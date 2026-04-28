import pandas as pd
import numpy as np
import joblib
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from sklearn.metrics.pairwise import cosine_similarity
import sys
import random
import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

# Download necessary NLTK data
for r in ['stopwords', 'punkt', 'wordnet', 'punkt_tab']:
    nltk.download(r, quiet=True)

class SmartChatbot:
    def __init__(self):
        try:
            # Load models
            # retrieval_tfidf_model.pkl is used for sentence questions (finding reference answers)
            self.retrieval_tfidf = joblib.load('retrieval_tfidf_model.pkl')
            # naive_bayes_model.pkl is used for MCQ option scoring
            self.nb_model = joblib.load('naive_bayes_model.pkl')
            
            # We use smart_assessment_model.pkl to get the Knowledge Base (question_index)
            # since the CSV data is not directly available.
            assessment_data = joblib.load('smart_assessment_model.pkl')
            self.kb = assessment_data.get('question_index')
            
            if self.kb is None:
                print("Error: Could not find Knowledge Base in smart_assessment_model.pkl")
                sys.exit(1)
            
            # Pre-calculate KB vectors for retrieval
            self.kb['question_clean'] = self.kb['question'].apply(self.preprocess)
            self.kb_vectors = self.retrieval_tfidf.transform(self.kb['question_clean'])
            
            self.lemmatizer = WordNetLemmatizer()
            self.stop_words = set(stopwords.words('english'))
            
            # Initialize Hugging Face Client for fallback
            self.hf_token = os.getenv("HF_TOKEN")
            if self.hf_token:
                # Remove any quotes or spaces that might have been added
                self.hf_token = self.hf_token.strip().strip('"').strip("'")
            
            self.hf_client = InferenceClient(
                token=self.hf_token
            ) if self.hf_token else None
            
            # MCQ patterns
            self.MCQ_PATTERNS = [
                r'\b[AaBbCcDd][\)\.]\s*\S+',
                r'\b[1234][\)\.]\s*\S+',
                r'\([AaBbCcDd]\)\s*\S+',
                r'\w+\s*/\s*\w+\s*/\s*\w+',
            ]
            
            print("✅ Smart Chatbot Initialized!")
            
        except Exception as e:
            print(f"Error during initialization: {e}")
            sys.exit(1)

    def preprocess(self, text):
        if not text or pd.isna(text):
            return ''
        text = str(text).lower()
        text = re.sub(r'[^a-z\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        tokens = word_tokenize(text)
        lemmatizer = WordNetLemmatizer()
        stop_words = set(stopwords.words('english'))
        return ' '.join(
            lemmatizer.lemmatize(t) for t in tokens
            if t not in stop_words and len(t) > 2
        )

    def is_mcq(self, text):
        for pattern in self.MCQ_PATTERNS:
            matches = re.findall(pattern, text)
            if len(matches) >= 2:
                return True
        return False

    def parse_mcq(self, text):
        text = text.strip()
        text = re.sub(r'\b1[\)\.]', 'A)', text)
        text = re.sub(r'\b2[\)\.]', 'B)', text)
        text = re.sub(r'\b3[\)\.]', 'C)', text)
        text = re.sub(r'\b4[\)\.]', 'D)', text)
        text = re.sub(r'\(([AaBbCcDd])\)', lambda m: m.group(1).upper()+')', text)
        text = re.sub(r'\b([AaBbCcDd])\.\s', lambda m: m.group(1).upper()+') ', text)

        option_pattern = r'\b([ABCD])\)'
        splits = re.split(option_pattern, text, flags=re.IGNORECASE)

        if len(splits) < 3:
            return {'question': text, 'options': {}}

        question_stem = splits[0].strip()
        options = {}
        for i in range(1, len(splits)-1, 2):
            letter = splits[i].upper()
            value = splits[i+1].strip().rstrip(',;') if i+1 < len(splits) else ''
            if letter in 'ABCD' and value:
                options[letter] = value
        return {'question': question_stem, 'options': options}

    def get_deepseek_response(self, user_question):
        """Fallback to DeepSeek R1 if local knowledge base fails."""
        print(f"DEBUG: Local KB match score too low. Falling back to DeepSeek-R1 for: '{user_question}'")
        
        # 1. Check if token is configured
        if not self.hf_token:
            return ("DeepSeek AI is currently unavailable because the API token (HF_TOKEN) is missing. "
                    "Please add your Hugging Face token to the .env file to enable AI fallback.")
        
        if not self.hf_client:
            return "DeepSeek AI client failed to initialize. Please check your internet connection and API token."
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Using chat_completion with an explicit model to satisfy the conversational task
                # Added a system prompt to help guide the model and improve response rate
                response = self.hf_client.chat_completion(
                    model="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
                    messages=[
                        {"role": "system", "content": "You are a helpful Science Assistant. Answer the user's question clearly and concisely."},
                        {"role": "user", "content": user_question}
                    ],
                    max_tokens=500,
                    temperature=0.7
                )
                
                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    if content and content.strip():
                        return content.strip()
                    else:
                        print(f"DEBUG: Attempt {attempt+1} - DeepSeek returned empty content.")
                        if attempt < max_retries - 1:
                            import time
                            time.sleep(1) # Wait a second before retry
                            continue
                        
                        return ("The AI (DeepSeek) processed your question but didn't return any text. "
                                "This can happen if the AI considers the topic restricted or if the model "
                                "is currently under heavy load. Please try rephrasing your question slightly.")
                else:
                    print(f"DEBUG: Attempt {attempt+1} - DeepSeek returned no choices.")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)
                        continue
                    return ("The AI service is currently busy and couldn't generate an answer. "
                            "Please wait a few seconds and try asking your question again.")
                
            except Exception as e:
                error_str = str(e).lower()
                print(f"DEBUG: Attempt {attempt+1} - Error calling DeepSeek: {error_str}")
                
                # If it's a 503 (loading) or 429 (rate limit), we should probably not retry immediately
                # but for other temporary network issues, we can try one more time
                
                # 2. Handle Token/Authorization issues
                if "401" in error_str or "unauthorized" in error_str or "invalid token" in error_str:
                    return ("Authentication Error: Your Hugging Face API token appears to be invalid or expired. "
                            "Please verify the HF_TOKEN in your .env file and ensure it has 'Read' permissions.")
                
                # 3. Handle Rate Limits
                elif "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                    return ("Rate Limit Reached: You've sent too many requests to the AI in a short period. "
                            "Free-tier tokens have strict limits. Please wait about 60 seconds before trying again.")
                
                # 4. Handle Model Loading (Cold Start)
                elif "503" in error_str or "loading" in error_str or "estimated_time" in error_str:
                    return ("The AI model is currently 'waking up' on the server. This happens when it hasn't "
                            "been used for a while. Please wait about 15-30 seconds and try again; it should be ready then.")
                
                # 5. Handle Network/Timeout
                elif "timeout" in error_str or "connection" in error_str:
                    if attempt < max_retries - 1:
                        continue
                    return ("Network Error: The request to the AI service timed out. This could be due to a "
                            "slow internet connection or server issues at Hugging Face. Please try again.")
                
                # 6. Fallback for other errors
                if attempt < max_retries - 1:
                    continue
                return f"AI Service Error: {str(e)}. This is likely a temporary issue with the DeepSeek provider."

    def get_plain_response(self, user_question):
        q_clean = self.preprocess(user_question)
        q_vec = self.retrieval_tfidf.transform([q_clean])
        sims = cosine_similarity(q_vec, self.kb_vectors).flatten()
        best_idx = sims.argmax()
        score = sims[best_idx]
        
        if score < 0.12:
            # TRIGGER FALLBACK HERE
            print(f"DEBUG: Match score {score:.4f} is below threshold 0.12. Using DeepSeek.")
            deepseek_answer = self.get_deepseek_response(user_question)
            return {
                "type": "plain",
                "status": "success",
                "match_confidence": round(float(score), 4),
                "source": "DeepSeek-R1",
                "fallback_reason": "Question not found in local science knowledge base (confidence too low).",
                "response": deepseek_answer
            }
        
        matched = self.kb.iloc[best_idx]['question']
        answer = self.kb.iloc[best_idx]['reference_answer']
        return {
            "type": "plain",
            "status": "success",
            "match_confidence": round(float(score), 4),
            "source": "Knowledge Base",
            "matched_question": matched,
            "response": answer
        }

    def answer_plain(self, user_question):
        res = self.get_plain_response(user_question)
        sep = '─' * 60
        print(f"\n{sep}")
        print("💬 PLAIN QUESTION DETECTED")
        print(sep)
        
        if res["status"] == "not_found":
            print(f"🤖 Bot: {res['response']}")
        else:
            print(f"🎯 Match Confidence: {res['match_confidence']:.1%}")
            print(f"🤖 Bot: Here is what I found:\n\n   {res['response']}")
        print(sep)

    def get_mcq_response(self, parsed):
        question_stem = parsed['question']
        options = parsed['options']

        if len(options) < 2:
            return {
                "type": "mcq",
                "status": "error",
                "response": "Could not parse enough options."
            }

        # Find reference answer for explanation
        q_clean = self.preprocess(question_stem)
        q_vec = self.retrieval_tfidf.transform([q_clean])
        sims = cosine_similarity(q_vec, self.kb_vectors).flatten()
        best_idx = sims.argmax()
        ref_answer = self.kb.iloc[best_idx]['reference_answer']

        # Signal 1: Similarity to reference answer
        ref_clean = self.preprocess(ref_answer)
        ref_vec = self.retrieval_tfidf.transform([ref_clean])

        option_scores = {}
        for letter, opt_text in options.items():
            opt_clean = self.preprocess(opt_text)
            opt_vec = self.retrieval_tfidf.transform([opt_clean])
            cos_sim = cosine_similarity(opt_vec, ref_vec).flatten()[0]
            
            option_scores[letter] = {
                'text': opt_text,
                'cos_sim': round(float(cos_sim), 4)
            }

        best_letter = max(option_scores, key=lambda l: option_scores[l]['cos_sim'])
        
        return {
            "type": "mcq",
            "status": "success",
            "source": "Knowledge Base",
            "match_confidence": option_scores[best_letter]['cos_sim'],
            "question": question_stem,
            "options": option_scores,
            "best_option": best_letter,
            "correct_answer": options[best_letter],
            "explanation": ref_answer
        }

    def answer_mcq(self, parsed):
        res = self.get_mcq_response(parsed)
        if res["status"] == "error":
            print(f"⚠️ {res['response']}")
            return

        sep = '─' * 60
        print(f"\n{sep}")
        print("📋 MCQ DETECTED")
        print(sep)
        print(f"❓ Question: {res['question']}")
        print(sep)
        for letter in sorted(res['options']):
            s = res['options'][letter]
            mark = "✅ ANSWER" if letter == res['best_option'] else ""
            print(f"  {letter}) {s['text'][:40]:<40} {mark}")
        
        print(sep)
        print(f"✅ Correct Answer: ({res['best_option']}) {res['correct_answer']}")
        print(f"\n📖 Explanation:\n   {res['explanation']}")
        print(sep)

    def run(self):
        print("\n" + "="*60)
        print("      🤖 SMART AUTO-DETECTING CHATBOT")
        print("="*60)
        print("Ask me a science question or an MCQ!")
        print("Type 'exit' to quit.\n")

        while True:
            try:
                user_input = input("🧑 You: ").strip()
                if user_input.lower() == 'exit':
                    break
                if not user_input:
                    continue

                if self.is_mcq(user_input):
                    parsed = self.parse_mcq(user_input)
                    self.answer_mcq(parsed)
                else:
                    self.answer_plain(user_input)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"An error occurred: {e}")

if __name__ == "__main__":
    bot = SmartChatbot()
    bot.run()
