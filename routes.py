from flask import Flask, render_template, request, Response, jsonify, session, send_from_directory, flash, redirect, url_for
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.vectorstores import FAISS
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain_community.llms import OpenAI
from langchain_community.chat_models import ChatOpenAI
import os
import openai
from langchain.chains.conversation.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from openai import OpenAI
from langchain.prompts import BaseChatPromptTemplate, PromptTemplate
from langchain.chains import LLMChain
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import HumanMessage, SystemMessage
from dotenv import load_dotenv
import requests
import json
import langchaindemoBlock_22_april as LCD
import threading
import queue
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain.chains import ConversationChain
from flask_caching import Cache
import uuid
import shutil 
from bs4 import BeautifulSoup
import urllib.request
from werkzeug.datastructures import FileStorage
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from langchain_community.document_loaders import YoutubeLoader
from flask_basicauth import BasicAuth

load_dotenv(dotenv_path="HUGGINGFACEHUB_API_TOKEN.env")
# Set the API key for OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI()

import io
import os


app = Flask(__name__)
app.secret_key = os.urandom(24)

app.config['BASIC_AUTH_REALM'] = 'realm'
app.config['BASIC_AUTH_USERNAME'] = os.getenv('BASIC_AUTH_USERNAME')
app.config['BASIC_AUTH_PASSWORD'] = os.getenv('BASIC_AUTH_PASSWORD')
basic_auth = BasicAuth(app)

app.config['CACHE_TYPE'] = 'FileSystemCache' 
app.config['CACHE_DIR'] = 'cache' # path to server cache folder
app.config['CACHE_THRESHOLD'] = 1000
cache = Cache(app)

def delete_faiss_indexes():
    """
    Deletes directories starting with 'faiss_index_' in the root directory of the app.
    """
    base_path = os.path.dirname(os.path.abspath(__file__))
    for item in os.listdir(base_path):
        dir_path = os.path.join(base_path, item)
        if os.path.isdir(dir_path) and item.startswith("faiss_index_"):
            print(f"Deleting directory: {dir_path}")
            shutil.rmtree(dir_path)

@app.route("/cron", methods=['POST'])
@basic_auth.required
def cron():
    delete_faiss_indexes()
    print("Deleted FAISS index")
    return "FAISS index directories deleted", 200

@app.route("/process_data", methods=["GET", "POST"])
def process_data():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())  # Create a unique session user_id if not exists

    if request.method == 'POST':
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        prompt = request.form.get("prompt")

        url_doc = request.form.get('url_doc')

        f = request.files.getlist('file')
        print("There is a file")

        if url_doc:
            if url_doc and ('www.youtube.com' in url_doc or 'youtu.be' in url_doc):
                loader = YoutubeLoader.from_youtube_url(
                url_doc, add_video_info=False)
                var_load = loader.load()
                raw_text = ''
                var = raw_text.join(document.page_content + '\n\n' for document in var_load)
                if var:
                    pdf_bytes = io.BytesIO()
                    c = canvas.Canvas(pdf_bytes, pagesize=A4)
                    text = c.beginText(40, 750)
                    text.setFont("Helvetica", 6)
                    lines = var.split('\n')
                    for line in lines:
                        text.textLine(line)
                    c.drawText(text)
                    c.showPage()
                    c.save()
                    pdf_bytes.seek(0)
                    # with open('extracted_content.pdf', 'wb') as pdf_file:
                    #     pdf_file.write(pdf_bytes.getvalue())
                    pdf_file_wrapper = FileStorage(stream=pdf_bytes, filename='extracted_content.pdf', content_type='application/pdf')
                    pdf_file_wrapper.seek(0)
                    f.append(pdf_file_wrapper)
                
            else:
                soup = BeautifulSoup(urllib.request.urlopen(url_doc).read())
                var = soup.get_text()
                print("Extracted text length:", len(var))  # Debug text length

                if var:
                    pdf_bytes = io.BytesIO()
                    c = canvas.Canvas(pdf_bytes, pagesize=A4)
                    text = c.beginText(40, 750)
                    text.setFont("Helvetica", 6)
                    lines = var.split('\n')
                    for line in lines:
                        text.textLine(line)
                    c.drawText(text)
                    c.showPage()
                    c.save()
                    pdf_bytes.seek(0)
                    # with open('extracted_content.pdf', 'wb') as pdf_file:
                    #     pdf_file.write(pdf_bytes.getvalue())
                    pdf_file_wrapper = FileStorage(stream=pdf_bytes, filename='extracted_content.pdf', content_type='application/pdf')
                    pdf_file_wrapper.seek(0)
                    f.append(pdf_file_wrapper)

        filename = [f_name.filename for f_name in f]
        print("Filename is::",filename)

        base_docsearch = None
        for file in f:
            file_content = io.BytesIO(file.read())
            # file_content = [io.BytesIO(fs.read()) for fs in f]
            print("LCD initiated!")
            try:
                docsearch = LCD.RAG(file_content,embeddings,file)
            except Exception as e:
                docsearch = None
                print("Error processing file:", str(e))
            if base_docsearch is None:
                base_docsearch = docsearch  # For the first file
            else:
                base_docsearch.merge_from(docsearch)  # Merge subsequent indexes

        if base_docsearch:
            base_docsearch.save_local(f"faiss_index_{session['user_id']}") 
            

            cache.set("user_id_cache", session['user_id'],timeout=0)
            cache.set(f"prompt_{session['user_id']}", prompt,timeout=0)

            return Response("Data processed!", mimetype='text/plain')

    else:
        f = None
        filename = None

    # Return the processed text in JSON format
    # return jsonify({"response": response['text']})
    return Response("Nothing", mimetype='text/plain')

@app.route("/decide", methods=["GET", "POST"])
def decide():
    if request.method == 'POST':
        scenario = request.form.get('scenario')
        print("Scenario type:",scenario)

        if scenario:
            user_id_cache = cache.get("user_id_cache")
            print(user_id_cache)

            prompt = cache.get(f"prompt_{user_id_cache}")
            print("Prompt loaded!:",prompt)

            try:
                llm = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0, streaming=True, verbose= True)
                embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
                load_docsearch = FAISS.load_local(f"faiss_index_{session['user_id']}",embeddings,allow_dangerous_deserialization=True)
                
                chain, docs_main, query = LCD.PRODUCE_LEARNING_OBJ_COURSE(prompt, load_docsearch, llm)
                print("1st Docs_main:",docs_main)
                response_LO_CA = chain({"input_documents": docs_main,"human_input": query})

                cache.set(f"scenario_{session['user_id']}", scenario,timeout=0)

                return Response(response_LO_CA['text'], mimetype='text/plain')
            except:
                print("Some Error!")

        else:
            print("None")
            
        return Response("OK", mimetype='text/plain')
    
@app.route("/generate_course", methods=["GET", "POST"])
def generate_course():
    if request.method == 'POST':
        learning_obj = request.form.get("learning_obj")
        content_areas = request.form.get("content_areas")

        if learning_obj and content_areas:
            user_id_cache = cache.get("user_id_cache")

            prompt = cache.get(f"prompt_{user_id_cache}")
            print("Prompt loaded!:",prompt)

            scenario = cache.get(f"scenario_{user_id_cache}")
            print("scenario loaded!:",scenario)

            try:
                embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
                load_docsearch = FAISS.load_local(f"faiss_index_{session['user_id']}",embeddings,allow_dangerous_deserialization=True)
                combined_prompt = f"{prompt}\n{learning_obj}\n{content_areas}"
                docs_main = LCD.RE_SIMILARITY_SEARCH(combined_prompt, load_docsearch)
                print("2nd Docs_main:",docs_main)
                print("combined_prompt",combined_prompt)

                llm = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0.1, streaming=True, verbose= True)
                response = LCD.TALK_WITH_RAG(scenario, content_areas, learning_obj, prompt, docs_main, llm)
            except Exception as e:
                print(f"An error occurred: {e}")
        
            index_file_path = f"faiss_index_{user_id_cache}"
            shutil.rmtree(index_file_path)
            print(f"faiss_index_{user_id_cache}")

            
            cache.delete(f"prompt_{user_id_cache}")
            cache.delete(f"scenario_{user_id_cache}")
            cache.delete("user_id_cache")

            return Response(response['text'], mimetype='text/plain')
        else:
            print("None")
        
        return Response("Some Error Try Again!", mimetype='text/plain')

if __name__ == '__main__':
    app.run()
