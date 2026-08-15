import base64
import io
import json
import os
import re
import sqlite3
import threading
import time
import queue
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import requests
import mss
from PIL import Image
import sounddevice as sd
import soundfile as sf
import pyttsx3
from faster_whisper import WhisperModel
from pynput import keyboard
import updater

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
KNOWLEDGE_DIR = APP_DIR / "knowledge"
SCREENSHOT_DIR = APP_DIR / "screenshots"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = DATA_DIR / "memory.db"

for p in (DATA_DIR, KNOWLEDGE_DIR, SCREENSHOT_DIR):
    p.mkdir(exist_ok=True)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

SYSTEM_PROMPT = """You are PAL-AI, a local AI gaming companion for Palworld.
Always communicate in English unless the user explicitly asks for another language.
Your role is to cooperate with the player, explain things, plan next steps, and remember useful information.
Keep spoken gameplay answers practical and concise. Act like a cooperative gaming companion:
notice immediate problems, suggest useful next actions, and relate advice to what the player is currently doing.
When a screenshot is attached, analyze the visible game state directly instead of asking the user to send a screenshot.
If you are uncertain about a Palworld fact, say that you are uncertain.
Do not invent exact stats, drops, coordinates, recipes, or game mechanics unless they are supported by the provided knowledge.
You may analyze screenshots that the user explicitly sends.
You never control the game, mouse, or keyboard automatically.
Use the player's saved memories and local knowledge files when relevant.
"""

class MemoryDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT DEFAULT 'auto'
        )""")
        self.conn.commit()
    def add_message(self, role, content):
        self.conn.execute("INSERT INTO messages(ts,role,content) VALUES(?,?,?)", (datetime.now().isoformat(timespec="seconds"), role, content)); self.conn.commit()
    def recent_messages(self, n=12):
        rows=self.conn.execute("SELECT role,content FROM messages ORDER BY id DESC LIMIT ?",(n,)).fetchall(); return [{"role":r,"content":c} for r,c in reversed(rows)]
    def add_memory(self, content, source="auto"):
        content=content.strip()
        if content:
            self.conn.execute("INSERT INTO memories(ts,content,source) VALUES(?,?,?)",(datetime.now().isoformat(timespec="seconds"),content,source)); self.conn.commit()
    def search_memories(self, query, limit=6):
        words=[w.lower() for w in re.findall(r"\w+",query) if len(w)>2]; rows=self.conn.execute("SELECT content FROM memories ORDER BY id DESC LIMIT 200").fetchall(); scored=[]
        for (text,) in rows:
            score=sum(1 for w in words if w in text.lower())
            if score: scored.append((score,text))
        scored.sort(key=lambda x:x[0],reverse=True); return [t for _,t in scored[:limit]]

class KnowledgeBase:
    def __init__(self, folder): self.folder=folder
    def chunks(self):
        out=[]
        for path in self.folder.rglob("*"):
            if path.suffix.lower() not in {".txt",".md",".json"}: continue
            try: text=path.read_text(encoding="utf-8",errors="ignore")
            except Exception: continue
            for block in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-ZÅÄÖ])",text):
                block=block.strip()
                if len(block)>=40: out.append((path.name,block[:1800]))
        return out
    def search(self, query, limit=5):
        terms=[w.lower() for w in re.findall(r"\w+",query) if len(w)>2]; scored=[]
        for filename,chunk in self.chunks():
            score=sum(chunk.lower().count(t) for t in terms)
            if score: scored.append((score,filename,chunk))
        scored.sort(key=lambda x:x[0],reverse=True); return scored[:limit]

class OllamaClient:
    def __init__(self, base_url): self.base=base_url.rstrip("/")
    def available(self):
        try: return requests.get(self.base+"/api/tags",timeout=3).ok
        except Exception: return False
    def chat(self, model, messages, images=None, timeout=180):
        msgs=list(messages)
        if images: msgs[-1]=dict(msgs[-1]); msgs[-1]["images"]=images
        r=requests.post(self.base+"/api/chat",json={"model":model,"messages":msgs,"stream":False},timeout=timeout); r.raise_for_status(); return r.json()["message"]["content"]

class PalworldServerAPI:
    def __init__(self,cfg): self.cfg=cfg
    def read_status(self):
        if not self.cfg.get("enabled"): return None
        base=self.cfg.get("base_url","").rstrip("/"); auth=None; user=self.cfg.get("username",""); pw=self.cfg.get("password","")
        if user or pw: auth=(user,pw)
        result={}
        for endpoint in ("info","players","metrics"):
            try:
                r=requests.get(f"{base}/{endpoint}",auth=auth,timeout=3); result[endpoint]=r.json() if r.ok else {"http_status":r.status_code}
            except Exception as e: result[endpoint]={"error":str(e)}
        return result

class Voice:
    def __init__(self):
        self.whisper=None; self.engine=None; self.lock=threading.Lock(); self.record_lock=threading.Lock(); self.stream=None; self.frames=[]; self.sample_rate=16000; self.record_started_at=None
    def ensure_stt(self):
        if self.whisper is None: self.whisper=WhisperModel(CONFIG.get("stt_model","small"),device=CONFIG.get("stt_device","cpu"),compute_type=CONFIG.get("stt_compute_type","int8"))
    def _transcribe_file(self,path):
        self.ensure_stt(); segments,_=self.whisper.transcribe(str(path),language="en",vad_filter=True); return " ".join(seg.text.strip() for seg in segments).strip()
    def record_and_transcribe(self,seconds):
        audio=sd.rec(int(seconds*self.sample_rate),samplerate=self.sample_rate,channels=1,dtype="float32"); sd.wait(); tmp=DATA_DIR/"last_voice.wav"; sf.write(tmp,audio,self.sample_rate); return self._transcribe_file(tmp)
    def start_ptt(self):
        with self.record_lock:
            if self.stream is not None: return False
            self.frames=[]; self.record_started_at=time.time()
            def callback(indata,frames,time_info,status): self.frames.append(indata.copy())
            self.stream=sd.InputStream(samplerate=self.sample_rate,channels=1,dtype="float32",callback=callback); self.stream.start(); return True
    def stop_ptt_and_transcribe(self):
        with self.record_lock:
            if self.stream is None: return ""
            stream=self.stream; self.stream=None; started=self.record_started_at or time.time(); self.record_started_at=None
        try: stream.stop(); stream.close()
        finally: duration=time.time()-started
        if duration<float(CONFIG.get("ptt_min_seconds",0.25)) or not self.frames: self.frames=[]; return ""
        import numpy as np
        audio=np.concatenate(self.frames,axis=0); self.frames=[]; tmp=DATA_DIR/"last_ptt.wav"; sf.write(tmp,audio,self.sample_rate); return self._transcribe_file(tmp)
    def speak(self,text):
        if not CONFIG.get("voice_enabled",True): return
        with self.lock:
            if self.engine is None:
                self.engine=pyttsx3.init(); self.engine.setProperty("rate",185)
                try:
                    for voice in self.engine.getProperty("voices"):
                        info=(getattr(voice,"name","")+" "+getattr(voice,"id","")+" "+str(getattr(voice,"languages","")).lower()).lower()
                        if "english" in info or "en-us" in info or "en-gb" in info: self.engine.setProperty("voice",voice.id); break
                except Exception: pass
            self.engine.say(re.sub(r"[#*_`]","",text)[:1200]); self.engine.runAndWait()

def capture_screen():
    with mss.mss() as sct:
        mon=sct.monitors[1]; shot=sct.grab(mon); img=Image.frombytes("RGB",shot.size,shot.rgb); path=SCREENSHOT_DIR/f"pal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"; img.save(path,quality=82); buf=io.BytesIO(); img.save(buf,format="JPEG",quality=72); return path,base64.b64encode(buf.getvalue()).decode("ascii")

class App:
    def __init__(self,root):
        self.root=root; self.root.title("PAL-AI v0.7 — GitHub Auto-Updater"); self.root.geometry("960x700"); self.db=MemoryDB(DB_PATH); self.kb=KnowledgeBase(KNOWLEDGE_DIR); self.ollama=OllamaClient(CONFIG["ollama_url"]); self.voice=Voice(); self.server=PalworldServerAPI(CONFIG.get("palworld_server_api",{})); self.turn_count=0; self.busy=False; self.ptt_active=False; self.ptt_listener=None; self._build(); self._setup_ptt(); ptt_note=f" Hold {CONFIG.get('ptt_key','j').upper()} for Push-to-Talk." if CONFIG.get("ptt_enabled",True) else ""; self._say_ui("PAL-AI","Ready. Type a question, use the microphone, or analyze the screen."+ptt_note)
    def _setup_ptt(self):
        if not CONFIG.get("ptt_enabled",True): return
        wanted=str(CONFIG.get("ptt_key","j")).lower()
        def key_name(key):
            try: return key.char.lower() if key.char else ""
            except Exception: return ""
        def on_press(key):
            if key_name(key)!=wanted or self.ptt_active or self.busy: return
            self.ptt_active=True
            try:
                if self.voice.start_ptt(): self.root.after(0,lambda:self.set_status(f"PTT: listening — release {wanted.upper()} to send"))
            except Exception as e: self.ptt_active=False; self.root.after(0,lambda:self._finish_error(f"PTT microphone error: {e}"))
        def on_release(key):
            if key_name(key)!=wanted or not self.ptt_active: return
            self.ptt_active=False; self.root.after(0,lambda:self.set_status("PTT: transcribing..."))
            def worker():
                try:
                    text=self.voice.stop_ptt_and_transcribe()
                    if not text: self.root.after(0,lambda:self.set_status("Ready")); return
                    self.root.after(0,lambda t=text:self.capture_and_ask(t) if self.is_screen_command(t) else self.ask(t))
                except Exception as e: self.root.after(0,lambda:self._finish_error(f"PTT error: {e}"))
            threading.Thread(target=worker,daemon=True).start()
        self.ptt_listener=keyboard.Listener(on_press=on_press,on_release=on_release); self.ptt_listener.daemon=True; self.ptt_listener.start()
    def _build(self):
        top=ttk.Frame(self.root,padding=8); top.pack(fill="x"); self.status=ttk.Label(top,text="Checking Ollama..."); self.status.pack(side="left"); ttk.Button(top,text="Check updates",command=self.check_updates).pack(side="right",padx=(6,0)); ttk.Button(top,text="Test Ollama",command=self.test_ollama).pack(side="right")
        self.chatbox=scrolledtext.ScrolledText(self.root,wrap=tk.WORD,state="disabled",font=("Segoe UI",10),padx=10,pady=10); self.chatbox.pack(fill="both",expand=True,padx=8,pady=4)
        input_frame=ttk.Frame(self.root,padding=8); input_frame.pack(fill="x"); self.entry=tk.Text(input_frame,height=3,wrap=tk.WORD,font=("Segoe UI",10)); self.entry.pack(side="left",fill="x",expand=True); self.entry.bind("<Control-Return>",lambda e:self.send_text()); ttk.Button(input_frame,text="Send (Ctrl+Enter)",command=self.send_text).pack(side="left",padx=6)
        btns=ttk.Frame(self.root,padding=(8,0,8,8)); btns.pack(fill="x"); ttk.Button(btns,text="🎙 Talk 6 s",command=self.voice_input).pack(side="left"); ttk.Label(btns,text=f"  PTT: hold {CONFIG.get('ptt_key','j').upper()}").pack(side="left"); ttk.Button(btns,text="👁 Analyze screen",command=self.screen_question).pack(side="left",padx=6); ttk.Button(btns,text="🧠 Remember...",command=self.remember_dialog).pack(side="left"); ttk.Button(btns,text="🔇/🔊 Voice",command=self.toggle_voice).pack(side="left",padx=6); ttk.Button(btns,text="🧹 Clear chat",command=self.clear_view).pack(side="right"); self.root.after(300,self.test_ollama)
        if CONFIG.get("updater",{}).get("auto_check_on_start",True): self.root.after(1200,lambda:self.check_updates(silent=True))
    def _say_ui(self,who,text): self.chatbox.configure(state="normal"); self.chatbox.insert("end",f"\n{who}: {text}\n"); self.chatbox.see("end"); self.chatbox.configure(state="disabled")
    def set_status(self,text): self.status.configure(text=text)
    def check_updates(self,silent=False):
        def worker():
            try:
                result=updater.check_for_update(); status=result.get("status")
                if status=="no_release":
                    if not silent:self.root.after(0,lambda:messagebox.showinfo("Updates","No GitHub Release has been published yet.")); return
                if status=="disabled": return
                if status=="up_to_date":
                    if not silent:self.root.after(0,lambda:messagebox.showinfo("Updates",f"PAL-AI {result.get('current')} is up to date.")); return
                if status=="update_available":
                    def ask():
                        if messagebox.askyesno("PAL-AI update",f"PAL-AI {result.get('latest')} is available.\n\n{result.get('notes','')}\n\nApply the update now?\nThe ZIP will be verified with SHA-256 before installation."):
                            try: updater.prepare_update(result["download_url"],result["latest"],result["sha256"]); messagebox.showinfo("PAL-AI update","Update prepared. PAL-AI will close and restart automatically."); self.root.after(300,self.root.destroy)
                            except Exception as e: messagebox.showerror("Update failed",str(e))
                    self.root.after(0,ask)
            except Exception as e:
                if not silent:self.root.after(0,lambda:messagebox.showerror("Update check failed",str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def test_ollama(self): self.set_status("Ollama: connected" if self.ollama.available() else "Ollama: not connected — run install.bat / start Ollama")
    def toggle_voice(self): CONFIG["voice_enabled"]=not CONFIG.get("voice_enabled",True); CONFIG_PATH.write_text(json.dumps(CONFIG,indent=2,ensure_ascii=False),encoding="utf-8"); self._say_ui("System","Voice output "+("ON" if CONFIG["voice_enabled"] else "OFF"))
    def clear_view(self): self.chatbox.configure(state="normal"); self.chatbox.delete("1.0","end"); self.chatbox.configure(state="disabled")
    def remember_dialog(self):
        win=tk.Toplevel(self.root); win.title("Save memory"); ttk.Label(win,text="What should PAL-AI remember?").pack(padx=10,pady=8); t=tk.Text(win,width=60,height=5); t.pack(padx=10,pady=4)
        def save(): self.db.add_memory(t.get("1.0","end").strip(),"manual"); win.destroy(); self._say_ui("System","Saved to memory.")
        ttk.Button(win,text="Save",command=save).pack(pady=8)
    def build_context(self,user_text):
        memories=self.db.search_memories(user_text); knowledge=self.kb.search(user_text,CONFIG.get("knowledge_results",5)); sections=[]
        if memories: sections.append("RELEVANT MEMORIES:\n- "+"\n- ".join(memories))
        if knowledge: sections.append("LOCAL PALWORLD KNOWLEDGE:\n"+"\n\n".join(f"[{fn}] {chunk}" for _,fn,chunk in knowledge))
        server_data=self.server.read_status()
        if server_data: sections.append("READ-ONLY DATA FROM PALWORLD DEDICATED SERVER:\n"+json.dumps(server_data,ensure_ascii=False)[:6000])
        return "\n\n".join(sections)
    def make_messages(self,user_text,extra_context=""):
        messages=[{"role":"system","content":SYSTEM_PROMPT}]+self.db.recent_messages(CONFIG.get("max_history_messages",12)); content=user_text+("\n\n"+extra_context if extra_context else ""); messages.append({"role":"user","content":content}); return messages
    def send_text(self):
        if self.busy:return
        text=self.entry.get("1.0","end").strip()
        if not text:return
        self.entry.delete("1.0","end"); self.capture_and_ask(text) if self.is_screen_command(text) else self.ask(text)
    def is_screen_command(self,text):
        if not CONFIG.get("voice_screen_commands",True):return False
        normalized=re.sub(r"\s+"," ",re.sub(r"[^a-z0-9' ]+"," ",text.lower())).strip(); phrases=CONFIG.get("screen_command_phrases",[])
        if any(p.lower() in normalized for p in phrases):return True
        return any(s in normalized.split() for s in ("screen","display","game","this")) and any(v in normalized.split() for v in ("look","see","analyze","analyse","check","scan","inspect"))
    def capture_and_ask(self,spoken_text=None):
        if self.busy:return
        self.set_status("Capturing screen...")
        try:path,img64=capture_screen()
        except Exception as e:self._finish_error(f"Could not capture screenshot: {e}");return
        prompt=f'The player said: "{spoken_text}"\nA screenshot of the player\'s current primary screen is attached. If Palworld is visible, analyze the current game state and answer directly. Give 1-3 useful next actions when appropriate. Do not ask for another screenshot.' if spoken_text else "Analyze my current screen and suggest what I should do next."
        self._say_ui("System",f"Screenshot captured: {path.name}"); self.ask(prompt,image_b64=img64)
    def ask(self,text,image_b64=None):
        if self.busy:return
        self.busy=True; self._say_ui("You",text); self.set_status("PAL-AI is thinking...")
        def worker():
            try:
                answer=self.ollama.chat(CONFIG["vision_model"] if image_b64 else CONFIG["model"],self.make_messages(text,self.build_context(text)),images=[image_b64] if image_b64 else None); self.db.add_message("user",text); self.db.add_message("assistant",answer); self.turn_count+=1; self.root.after(0,lambda:self._finish_answer(answer))
                if self.turn_count%int(CONFIG.get("auto_memory_every_turns",4))==0:threading.Thread(target=self.extract_memory,daemon=True).start()
            except Exception as e:self.root.after(0,lambda:self._finish_error(f"Error: {e}"))
        threading.Thread(target=worker,daemon=True).start()
    def _finish_answer(self,answer): self._say_ui("PAL-AI",answer); self.set_status("Ready"); self.busy=False; threading.Thread(target=self.voice.speak,args=(answer,),daemon=True).start()
    def _finish_error(self,msg): self._say_ui("System",msg); self.set_status("Error"); self.busy=False
    def extract_memory(self):
        try:
            recent=self.db.recent_messages(8); prompt="Read the conversation and extract only stable information useful later: preferences, goals, important Pals/equipment/bases, or decisions. Reply with at most 4 short bullet points."; mem=self.ollama.chat(CONFIG["model"],[{"role":"system","content":prompt},{"role":"user","content":json.dumps(recent,ensure_ascii=False)}],timeout=120).strip()
            if len(mem)>10:self.db.add_memory(mem,"auto")
        except Exception:pass
    def voice_input(self):
        if self.busy:return
        self.set_status("Listening...")
        def worker():
            try:
                text=self.voice.record_and_transcribe(CONFIG.get("record_seconds",6)); self.root.after(0,lambda t=text:self.capture_and_ask(t) if self.is_screen_command(t) else self.ask(t)) if text else self.root.after(0,lambda:self._finish_error("I couldn't hear anything clearly."))
            except Exception as e:self.root.after(0,lambda:self._finish_error(f"Microphone error: {e}"))
        threading.Thread(target=worker,daemon=True).start()
    def screen_question(self): self.capture_and_ask("Please analyze my screen and tell me what I should pay attention to.")

if __name__=="__main__":
    root=tk.Tk(); app=App(root); root.mainloop()
