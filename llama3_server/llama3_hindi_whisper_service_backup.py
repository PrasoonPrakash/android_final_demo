# SET export NO_PROXY=localhost,127.0.0.1
from transformers import AutoModelForCausalLM, AutoTokenizer
from fastapi import FastAPI
from pydantic import BaseModel
import torch, librosa
from typing import List
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from transformers import pipeline

DEVICE = 'cuda'
assert torch.cuda.is_available(), "CUDA not available"

# Initialize FastAPI
app = FastAPI()

# Load the model and tokenizer
model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token_id = tokenizer.eos_token_id
model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.bfloat16)
model = model.to(DEVICE)
print('Model loaded successfully')

transcribe = pipeline(
    task="automatic-speech-recognition", model="vasista22/whisper-hindi-large-v2", chunk_length_s=30, device=DEVICE
)
transcribe.model.config.forced_decoder_ids = transcribe.tokenizer.get_decoder_prompt_ids(language="hi", task="transcribe")
transcribe.model.config.suppress_tokens = None


class Message(BaseModel):
    role: str
    content: str


class ChatInput(BaseModel):
    messages: List[Message]
    max_new_tokens: int = 50
    temperature: float = 1e-4


def get_model_output(messages, max_new_tokens, temperature):
    model_inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
    model_inputs = {k: v.to(DEVICE) for k, v in model_inputs.items()}
        
    # Generate output
    outputs = model.generate(**model_inputs, max_new_tokens=max_new_tokens, temperature=temperature)
    
    # Decode output
    generated_text = tokenizer.decode(outputs[0][model_inputs['input_ids'].size(1):]).split('<|eot_id|>')[0].strip()
    # generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    return generated_text


@app.post("/generate/")
def generate_text(input: ChatInput):
    # Concatenate messages
    messages = [{'role': msg.role, 'content': msg.content} for msg in input.messages]
    temperature = input.temperature
    max_new_tokens = input.max_new_tokens
    try:
        generated_text = get_model_output(messages, max_new_tokens, temperature)
    except Exception as e:
        print('Following error occured during execution of the Llama3 model\n' + str(e))
        generated_text = 'ERROR!'

    return {"output": generated_text}


class TranscriptionInput(BaseModel):
    audio_file: str = 'dummy.mp4'


def run_whisper(audio_file):
    transcription = transcribe(audio_file)["text"]

    return transcription


@app.post("/transcribe/")
def transcribe_audio(input: TranscriptionInput):
    audio_file = input.audio_file
    try:
        ret = run_whisper(audio_file)
    except Exception as e:
        print('Following error occured during execution of the Whisper model\n' + str(e))
        ret = 'ERROR!'

    return {'output': ret}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
