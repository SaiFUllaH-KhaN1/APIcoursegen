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
import langchaindemoBlock as LCD
import threading
import queue
from langchain.chains.question_answering import load_qa_chain
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain.chains import ConversationChain
# load_dotenv(dotenv_path="E:\downloads\THINGLINK\dante\HUGGINGFACEHUB_API_TOKEN.env")
# # Set the API key for OpenAI
# openai.api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI()
import io
import os



app = Flask(__name__)
app.secret_key = '123'

@app.route("/process_data", methods=["GET", "POST"])
def process_data():

    if request.method == 'POST':
        prompt = request.form.get("prompt")
        scenario = request.form.get('scenario')

        f = request.files.getlist('file')
        print("There is a file")

        filename = [f_name.filename for f_name in f]
        print("Filename is::",filename)

        file_content = [io.BytesIO(fs.read()) for fs in f]
        docsearch = LCD.RAG(file_content)
        docsearch.save_local("faiss_index")

        llm = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0, streaming=True, verbose= True)
        embeddings = OpenAIEmbeddings()
        load_docsearch = FAISS.load_local("faiss_index",embeddings)

        chain, docs_main, query, subject_name = LCD.TALK_WITH_RAG(prompt, load_docsearch,llm,scenario)
        response = chain({"input_documents": docs_main,"subject_name": subject_name,"human_input": query})
        session['response'] = response['text']
    else:
        f = None
        filename = None

    # Return the processed text in JSON format
    # return jsonify({"response": response['text']})
    return Response(response['text'], mimetype='text/plain')

# @app.route("/json", methods=["GET", "POST"])
# def json():
#     if request.method == 'POST':
#         data = request.json
#         json = data.get('json')
#         if json:
#             response_to_convert = session['response']
#             llmsx = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0, streaming=True, verbose=True)
#             graphml_chain = LCD.GENERATE_GRAPHML(response_to_convert,llmsx)
#             json_output = graphml_chain.run(text=response_to_convert)
#             # response_data = json.loads(data['response'])
#         return Response(json_output, mimetype='text/plain')

if __name__ == '__main__':
    app.run()
