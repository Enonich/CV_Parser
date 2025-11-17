
import sys
import os
import json
import yaml
import argparse
import threading
import time
from pathlib import Path
from collections import deque

# Platform-specific import for keyboard input
IS_WINDOWS = os.name == 'nt'
if IS_WINDOWS:
    import msvcrt
else:
    import select
    import tty
    import termios

from pymongo import MongoClient
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.schema import Document

# Voice libraries
import sounddevice as sd
import numpy as np
import whisper
import pyttsx3
from scipy.io import wavfile
import torch

# --- 1. CONTEXT BUILDER ---
class CVScoringContext:
    """
    Builds context for the RAG agent by loading CV, JD, and scoring results.
    """
    def __init__(self, cv_id, jd_id, cv_collection, jd_collection, company_name: str = None):
        self.cv_id = cv_id
        self.jd_id = jd_id
        self.company_name = company_name
        self.cv_collection = cv_collection
        self.jd_collection = jd_collection
        self.cv_data = None
        self.jd_data = None

    @staticmethod
    def safe_join(value, default="N/A"):
        if value is None: return default
        if isinstance(value, list): return ', '.join(str(v) for v in value) if value else default
        return str(value)

    def load_cv_data(self):
        query = {"cv_id": self.cv_id}
        self.cv_data = self.cv_collection.find_one(query)
        if not self.cv_data:
            try:
                from bson import ObjectId
                if isinstance(self.cv_id, str) and len(self.cv_id) == 24:
                    query = {"_id": ObjectId(self.cv_id)}
                else:
                    query = {"_id": self.cv_id}
                self.cv_data = self.cv_collection.find_one(query)
            except: pass
        if not self.cv_data: raise ValueError(f"CV not found with ID: {self.cv_id}")
        return self.cv_data

    def load_jd_data(self):
        query = {"jd_id": self.jd_id}
        if self.company_name: query["company_name"] = self.company_name
        self.jd_data = self.jd_collection.find_one(query)
        if not self.jd_data:
            try:
                from bson import ObjectId
                if isinstance(self.jd_id, str) and len(self.jd_id) == 24:
                    query = {"_id": ObjectId(self.jd_id)}
                else:
                    query = {"_id": self.jd_id}
                if self.company_name: query["company_name"] = self.company_name
                self.jd_data = self.jd_collection.find_one(query)
            except: pass
        if not self.jd_data: raise ValueError(f"JD not found with ID: {self.jd_id}")
        return self.jd_data

    def build_context_document(self):
        if not self.cv_data or not self.jd_data:
            self.load_cv_data()
            self.load_jd_data()
        
        # This is a simplified version for brevity. The full version is in the notebook.
        return f"""
        CV for {self.cv_data.get('name', 'N/A')}:
        Skills: {self.safe_join(self.cv_data.get('skills'))}
        Summary: {self.cv_data.get('summary', 'N/A')}

        Job Description for {self.jd_data.get('job_title', 'N/A')}:
        Required Skills: {self.safe_join(self.jd_data.get('required_skills'))}
        """

    def get_summary(self):
        if not self.cv_data or not self.jd_data:
            self.load_cv_data()
            self.load_jd_data()
        return {
            "candidate_name": self.cv_data.get('name', 'N/A'), "cv_id": self.cv_id,
            "job_title": self.jd_data.get('job_title', 'N/A'), "jd_id": self.jd_id,
            "company": self.jd_data.get('company_name', 'N/A')
        }

# --- 2. RAG ENGINE ---
class CVExplainabilityAgent:
    """
    RAG-based agent that explains CV scoring decisions.
    """
    def __init__(self, context: CVScoringContext, llm, embeddings, config, company_name: str = None):
        self.context = context
        self.company_name = company_name
        self.llm = llm
        self.embeddings = embeddings
        self.config = config
        self.vector_store = None
        self.qa_chain = None
        self.context_text = self.context.build_context_document()
        self._setup_vector_store()
        self._setup_qa_chain()

    def _setup_vector_store(self):
        cv_persist_dir = self.config["chroma"]["cv_persist_dir"]
        cv_collection_name = self.config["chroma"]["cv_collection_name"]
        if self.company_name:
            # Assumes backend.core.identifiers is available or simplified
            company_fragment = "".join(e for e in self.company_name if e.isalnum()).lower()
            cv_collection_name = f"{company_fragment}_cv_sections"
            cv_persist_dir = os.path.join(cv_persist_dir, company_fragment)
        
        try:
            self.vector_store = Chroma(
                collection_name=cv_collection_name,
                embedding_function=self.embeddings,
                persist_directory=cv_persist_dir
            )
            print(f"✅ Connected to ChromaDB: {cv_collection_name}")
        except Exception as e:
            print(f"⚠️ Could not connect to ChromaDB: {e}. Creating in-memory store.")
            docs = [Document(page_content=self.context_text, metadata={"source": "context"})]
            self.vector_store = Chroma.from_documents(documents=docs, embedding=self.embeddings)

    def _setup_qa_chain(self):
        template = """You are an AI assistant helping HR recruiters understand CV scoring.
        Context: {context}
        Question: {question}
        Answer:"""
        PROMPT = PromptTemplate(template=template, input_variables=["context", "question"])
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm, chain_type="stuff",
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 3}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )
        print("✅ QA Chain initialized")

    def ask(self, question: str):
        result = self.qa_chain.invoke({"query": question})
        return {"question": question, "answer": result["result"], "sources": result["source_documents"]}

    def chat(self):
        print("\n" + "="*60 + "\nCV SCORING EXPLAINABILITY AGENT (TEXT MODE)\n" + "="*60)
        summary = self.context.get_summary()
        print(f"\nCandidate: {summary['candidate_name']} | Job: {summary['job_title']}\n")
        while True:
            question = input("💬 HR: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Ending session.")
                break
            if not question: continue
            print("\n🤖 Agent: ", end="", flush=True)
            result = self.ask(question)
            print(result["answer"])

# --- 3. VOICE MODULES ---
class SpeechToText:
    def __init__(self, model_name="base", sample_rate=16000):
        print(f"Loading Whisper model: {model_name}...")
        self.model = whisper.load_model(model_name)
        self.sample_rate = sample_rate
        print(f"✅ Whisper {model_name} model loaded")

    def transcribe_audio(self, audio_data):
        print("🔄 Transcribing...")
        result = self.model.transcribe(audio_data, fp16=False)
        text = result["text"].strip()
        print(f"📝 Transcribed: \"{text}\"")
        return text

class TextToSpeech:
    def __init__(self, rate=150, volume=0.9):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', rate)
        self.engine.setProperty('volume', volume)
        print("✅ TTS engine initialized")

    def speak(self, text):
        print(f"🔊 Speaking: \"{text[:60]}...\"")
        self.engine.say(text)
        self.engine.runAndWait()

class VoiceActivityDetector:
    def __init__(self, sample_rate=16000, threshold=0.5, min_silence_duration=0.8):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_silence_duration = min_silence_duration
        self.vad_chunk_size = 512
        
        print("Loading Silero VAD model...")
        self.model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False
        )
        print("✅ Silero VAD loaded")

    def is_speech(self, audio_chunk):
        if len(audio_chunk) != self.vad_chunk_size: return False
        audio_tensor = torch.from_numpy(audio_chunk).float()
        speech_prob = self.model(audio_tensor, self.sample_rate).item()
        return speech_prob > self.threshold

    def record_until_silence(self, max_duration=30):
        print("\n🎤 Listening... (speak when ready, I'll detect it automatically)")
        recording_chunk_duration = 0.1
        recording_chunk_size = int(recording_chunk_duration * self.sample_rate)
        max_chunks = int(max_duration / recording_chunk_duration)
        
        audio_buffer = []
        speech_started = False
        silence_duration = 0.0
        
        stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32')
        stream.start()

        for _ in range(max_chunks):
            chunk, overflowed = stream.read(recording_chunk_size)
            if overflowed: print("⚠️ Audio buffer overflow!")
            chunk = chunk.flatten()
            
            has_speech_in_chunk = any(
                self.is_speech(chunk[j:j + self.vad_chunk_size])
                for j in range(0, len(chunk), self.vad_chunk_size)
                if j + self.vad_chunk_size <= len(chunk)
            )
            
            if has_speech_in_chunk:
                if not speech_started:
                    print("🗣️ Speech detected! Recording...")
                    speech_started = True
                silence_duration = 0.0
                audio_buffer.append(chunk)
            elif speech_started:
                silence_duration += recording_chunk_duration
                audio_buffer.append(chunk)
                if silence_duration >= self.min_silence_duration:
                    print(f"✅ Silence detected. Recording stopped.")
                    break
        
        stream.stop()
        stream.close()
        if not speech_started:
            print("⚠️ No speech detected.")
            return None
        
        return np.concatenate(audio_buffer)

# --- 4. VOICE-ENABLED AGENT ---
class HandsFreeVoiceAgent(CVExplainabilityAgent):
    def __init__(self, *args, whisper_model="base", speech_rate=150, vad_threshold=0.5, **kwargs):
        super().__init__(*args, **kwargs)
        print("\n🎙️ Initializing voice capabilities...")
        self.stt = SpeechToText(model_name=whisper_model)
        self.tts = TextToSpeech(rate=speech_rate)
        self.vad = VoiceActivityDetector(
            sample_rate=self.stt.sample_rate,
            threshold=vad_threshold
        )
        print("✅ Hands-free agent ready!")

    def hands_free_chat(self, max_question_duration=30):
        print("\n" + "="*60 + "\nHANDS-FREE VOICE AGENT\n" + "="*60)
        summary = self.context.get_summary()
        welcome = f"Hello! I'm ready to answer questions about {summary['candidate_name']}'s application. Just start speaking."
        print(f"\n🤖 Agent: {welcome}")
        self.tts.speak(welcome)

        while True:
            try:
                audio = self.vad.record_until_silence(max_duration=max_question_duration)
                if audio is None: continue
                
                question = self.stt.transcribe_audio(audio)
                if any(word in question.lower() for word in ['goodbye', 'quit', 'exit', 'bye']):
                    goodbye = "Goodbye! Have a great day!"
                    print(f"\n🤖 Agent: {goodbye}"); self.tts.speak(goodbye)
                    break
                
                if not question or len(question.strip()) < 3:
                    prompt = "I didn't catch that. Please try again."
                    print(f"\n🤖 Agent: {prompt}"); self.tts.speak(prompt)
                    continue

                print(f"\n🎤 HR: {question}")
                print("🤖 Agent: ", end="", flush=True)
                result = self.ask(question)
                answer = result["answer"]
                print(answer)
                self.tts.speak(answer)
                print("\n" + "-"*60 + "\nReady for next question...")

            except KeyboardInterrupt:
                goodbye = "Session ended. Goodbye!"
                print(f"\n🤖 Agent: {goodbye}"); self.tts.speak(goodbye)
                break
            except Exception as e:
                error_msg = f"An error occurred: {e}"
                print(f"\n❌ {error_msg}"); self.tts.speak("I encountered an error.")

# --- 5. MAIN EXECUTION ---
def main():
    parser = argparse.ArgumentParser(description="Run the CV Explainability Agent.")
    parser.add_argument("mode", choices=["text", "voice"], help="Mode to run the agent in ('text' or 'voice').")
    args = parser.parse_args()

    # Load config
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Setup connections
    mongo_client = MongoClient(config["mongodb"]["connection_string"])
    cv_collection = mongo_client[config["mongodb"]["cv_db_name"]][config["mongodb"]["cv_collection_name"]]
    jd_collection = mongo_client[config["mongodb"]["jd_db_name"]][config["mongodb"]["jd_collection_name"]]
    
    llm = Ollama(model=config.get("llm_model", "llama3.2:latest"), base_url=config.get("ollama_url", "http://localhost:11434"))
    embeddings = OllamaEmbeddings(model=config["embedding"]["model"], base_url=config.get("ollama_url", "http://localhost:11434"))

    # Get sample data
    sample_cv = cv_collection.find_one()
    sample_jd = jd_collection.find_one()
    if not sample_cv or not sample_jd:
        print("❌ No CVs or JDs found in the database. Please add data first.")
        return

    cv_id = sample_cv.get('cv_id') or sample_cv.get('_id')
    jd_id = sample_jd.get('jd_id') or sample_jd.get('_id')
    company_name = sample_jd.get('company_name')

    # Create context
    context = CVScoringContext(cv_id, jd_id, cv_collection, jd_collection, company_name)

    if args.mode == "text":
        agent = CVExplainabilityAgent(context, llm, embeddings, config, company_name)
        agent.chat()
    elif args.mode == "voice":
        agent = HandsFreeVoiceAgent(
            context=context, llm=llm, embeddings=embeddings, config=config,
            company_name=company_name,
            whisper_model="base",
            speech_rate=160,
            vad_threshold=0.5
        )
        agent.hands_free_chat()

if __name__ == "__main__":
    # Add parent directory to path to allow imports from 'backend'
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
