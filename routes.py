# from gevent import monkey
# monkey.patch_all()
from flask import g, Flask, render_template, request, Response, jsonify, session, send_from_directory, flash, redirect, url_for
from prompt_logics import logger
import jwt
from langchain_community.vectorstores import FAISS
import os
from dotenv import load_dotenv
import json
import prompt_logics as LCD
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
import base64
import time
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
import google.generativeai as genai
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS
from functools import wraps
import io
import openai
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse, urljoin

import traceback
import fitz
import validators
import sys, socket
import asyncio
# from gevent.pywsgi import WSGIServer # in local development use, for gevent in local served
# from langchain_community.chat_models import ChatLiteLLM

load_dotenv(dotenv_path="E:\downloads\THINGLINK\dante\HUGGINGFACEHUB_API_TOKEN.env")

openai.api_type = os.getenv("OPENAI_API_TYPE")
openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")

os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")
# genai.configure(api_key=os.environ["GOOGLE_API_KEY"])


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')


# Configuration for the cache directory
cache_dir = 'cache'

# Check if the cache directory exists, and create it if it does not
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    logger.info(f"Cache directory '{cache_dir}' was created.")
else:
    logger.info(f"Cache directory '{cache_dir}' already exists.")

app.config['BASIC_AUTH_REALM'] = 'realm'
app.config['BASIC_AUTH_USERNAME'] = os.getenv('BASIC_AUTH_USERNAME')
app.config['BASIC_AUTH_PASSWORD'] = os.getenv('BASIC_AUTH_PASSWORD')
basic_auth = BasicAuth(app)

app.config['CACHE_TYPE'] = 'FileSystemCache' 
app.config['CACHE_DIR'] = 'cache' # path to server cache folder
app.config['CACHE_THRESHOLD'] = 1000
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'

cache = Cache(app)

allowed_origins = [
    "https://thinglink.local",
    "https://thinglink.local:3000",
    "https://sandbox.thinglink.com",
    "https://thinglink.com",
    "https://www.thinglink.com"
]

# Configure CORS for multiple routes with specific settings
cors = CORS(app, supports_credentials=True, resources={
    r"/process_data": {"origins": allowed_origins},
    r"/process_data_without_file": {"origins": allowed_origins},
    r"/decide": {"origins": allowed_origins},
    r"/decide_without_file": {"origins": allowed_origins},
    r"/generate_course": {"origins": allowed_origins},
    r"/generate_course_without_file": {"origins": allowed_origins},
    r"/find_images": {"origins": allowed_origins}
})

### TOKEN DECORATORS ###
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or 'Bearer ' not in auth_header:
            logger.critical("message: Missing or malformed token")
            return jsonify({"message": "Missing or malformed token"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            g.user_uuid = decoded['uuid4']
            logger.info(f"Token Decoded Success!:{g.user_uuid}") # NOT FOR PRODUCTION
        except jwt.ExpiredSignatureError:
            logger.critical("message: Token has expired")
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            logger.critical("message: Invalid token")
            return jsonify({"message": "Invalid token"}), 401
        except Exception as e:
            logger.critical(f"message: Invalid token: {str(e)}")
            return jsonify({"message": "Error for Token : " + str(e)}), 401
        
        return f(*args, **kwargs)
    return decorated


### MANUAL DELETION OF all folders starting with faiss_index_ ###
def delete_indexes():
    """
    Deletes directories starting with 'faiss_index_' in the root directory of the app.
    """
    base_path = os.path.dirname(os.path.abspath(__file__))
    for item in os.listdir(base_path):
        dir_path = os.path.join(base_path, item)
        if os.path.isdir(dir_path) and item.startswith("faiss_index_"):
            logger.info(f"Deleting Faiss directory: {dir_path}")
            shutil.rmtree(dir_path)
        elif os.path.isdir(dir_path) and item.startswith("imagefolder_"):
            logger.info(f"Deleting image directory: {dir_path}")
            shutil.rmtree(dir_path)
        elif os.path.isdir(dir_path) and item.startswith("audio_"):
            logger.info(f"Deleting audio directory: {dir_path}")
            shutil.rmtree(dir_path)
        elif os.path.isdir(dir_path) and item.startswith("pdf_dir"):
            logger.info(f"Deleting pdf directory: {dir_path}")
            shutil.rmtree(dir_path)

@app.route("/cron", methods=['POST'])
@basic_auth.required
def cron():
    delete_indexes()
    logger.info("Deleted FAISS index")
    return jsonify(message="FAISS and imagefolder and audio index directories deleted")
###     ###     ### 

### SCHEDULED DELETION OF folders of imagefolder_ and faiss_index_ ###
def delete_old_directories():
    time_to_delete_files_older_than = timedelta(hours=6)
    logger.info(f"Scheduler is running the delete_old_directories function to delete files older than {time_to_delete_files_older_than}.")
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    for item in os.listdir(base_path):
        dir_path = os.path.join(base_path, item)
        if os.path.isdir(dir_path) and item.startswith("faiss_index_") or item.startswith("imagefolder_") or item.startswith("audio_") or item.startswith("pdf_dir"):
            # Check if directory is older than a specified time
            dir_age = datetime.fromtimestamp(os.path.getmtime(dir_path))
            if datetime.now() - dir_age > time_to_delete_files_older_than:
                logger.info(f"Deleting directory: {dir_path}, it has modified date of {dir_age}")
                shutil.rmtree(dir_path)
###     ###     ###

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("0.0.0.0", 47200))
except socket.error:
    logger.info("!!!scheduler already started, DO NOTHING")
else:
    scheduler = BackgroundScheduler()
    scheduler.add_job(delete_old_directories, 'interval', hours=6)
    scheduler.start()

# Configuration for the audio directory
audio_dir = 'audio_files'
# Check if the cache directory exists, and create it if it does not
if not os.path.exists(audio_dir):
    os.makedirs(audio_dir, exist_ok=True)
    logger.info(f"Audio directory '{audio_dir}' was created.")
else:
    logger.info(f"Audio directory '{audio_dir}' already exists.")


@app.route("/process_data", methods=["GET", "POST"])
def process_data():

    if request.method == 'POST':
        start_time = time.time() # Timer starts at the Post

        # Create a unique session user_id if not exists
        session_var = str(uuid.uuid4())
        
        # getting requests from frontend
        
        model_type = request.args.get('model', 'azure') # to set default model
        model_name = request.args.get('modelName', 'gpt') # to set default model name
        model_local_embed = request.args.get('localEmbed', 'no') # to set default model state
        
        user_agents = request.headers.get('User-Agent') # a user agent of user from frontend if frontend allows
        if not user_agents:
            user_agents = [
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15',
                        'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
                        'Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko'
                        ]
            logger.info(f"user_agent alternate: {user_agents}")
        else:
            logger.info(f"user_agent from client: {user_agents}")
        
        prompt = request.form.get("prompt")
        url_doc = request.form.get('url_doc')
        f = request.files.getlist('file')
        logger.info("There is a File")

        language = request.form.get("language","english").lower()
        allowed_languages = ["english","finnish","spanish","german","italian","french"]

        if language not in allowed_languages:
            logger.error("Invalid Language Selected. Select out of english,finnish,spanish,german,italian or french.")
            return jsonify(error="Invalid Language Selected. Select out of english,finnish,spanish,german,italian or french.")
        else:
            logger.info(f"Language Selected is:{language}")

        filenames_check = [file.filename for file in f if file.filename != '']
        if not filenames_check and not url_doc:
            return redirect(url_for("process_data_without_file", prompt=prompt, language=language, session_var=session_var, start_time=start_time))

        output_path = f"./imagefolder_{session_var}"
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        if url_doc: 
            if validators.url(url_doc): # checks if url there and is valid
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
                        pdf_file_wrapper = FileStorage(stream=pdf_bytes, filename=f'extracted_content{session_var}.pdf', content_type='application/pdf') # still not unique for the same session so either url or youtube url processed at the same time
                        pdf_file_wrapper.seek(0)
                        f.append(pdf_file_wrapper)
                    
                else:
                    def fetch_url(url):
                        for user_agent in user_agents:
                            headers = {'User-Agent': user_agent}
                            try:
                                request = urllib.request.Request(url, headers=headers)
                                response = urllib.request.urlopen(request, timeout=3)
                                soup = BeautifulSoup(response.read(), 'html.parser')
                                var = soup.get_text()
                                logger.info(f"Extracted text length: {len(var)}")
                                return  var, soup
                            except (HTTPError, URLError) as e:
                                logger.error(f"Error with {user_agent}: {str(e)}")
                                continue  # Try the next user agent in case of an error

                    # Test the function with a given URL
                    try:
                        var, soup = fetch_url(url_doc)
                    except Exception as e:
                        logger.error(f"Error with URL processing:{str(e)}")
                        return jsonify(error=f"Error with URL processing:{str(e)}")

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
                        pdf_file_wrapper = FileStorage(stream=pdf_bytes, filename=f'extracted_content{session_var}.pdf', content_type='application/pdf')
                        pdf_file_wrapper.seek(0)
                        f.append(pdf_file_wrapper) # here the file is formed and appended with other user uploaded files
                        
                        # Starting Image extraction now
                        parsed_url = urlparse(url_doc) # parse url for getting base url only
                        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                        LCD.URL_IMG_EXTRACT(soup, session_var, base_url) # images extracted by this function
            else:
                logger.warning(f"Invalid URL Spotted! {url_doc}")
                return jsonify(error=f"Invalid URL Spotted! {url_doc}")

        filename = [f_name.filename for f_name in f]
        logger.info(f"Filename is::{filename}")

        base_docsearch = None
        for file in f:

            filename = file.filename
            logger.info(f"filename is {filename}")
            extension = filename.rsplit('.', 1)[1].lower()
            temp_path_audio = os.path.join(audio_dir, f"audio_{session_var}_{filename}") # declared here for overcoming reference before assignment error

            if not os.path.exists(f"pdf_dir{session_var}"):
                os.makedirs(f"pdf_dir{session_var}", exist_ok=True)         
            
            temp_pdf_file = os.path.join(f"pdf_dir{session_var}", f"{session_var}{filename}")
            if extension =="mp3":
                logger.info("temp_path_audio",temp_path_audio)
                file.save(temp_path_audio)
            elif extension =="pdf" and f'extracted_content{session_var}.pdf' not in filename:
                file.save(temp_pdf_file)
            ## AUDIO CHECK END    

            file_content = io.BytesIO(file.read())
            # file_content = [io.BytesIO(fs.read()) for fs in f]
            logger.info("LCD initiated!")
            try:
                if model_type == 'gemini' and model_local_embed == 'no':
                    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001" )
                elif model_type == 'azure' and model_local_embed == 'no':
                    embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-ada-002")

                logger.info(f"Using embeddings of {embeddings}")
                docsearch = LCD.RAG(file_content,embeddings,file,session_var, temp_path_audio,filename, extension, language, temp_pdf_file)
                if os.path.exists(f"pdf_dir{session_var}"):
                    shutil.rmtree(f"pdf_dir{session_var}")
            except Exception as e:
                docsearch = None
                logger.error(f"Error processing file:{str(e)}")
                logger.error(traceback.format_exc())
                if os.path.exists(f"pdf_dir{session_var}"):
                    shutil.rmtree(f"pdf_dir{session_var}")
                return jsonify(error=f"Error processing file:{str(e)}")
            if base_docsearch is None:
                base_docsearch = docsearch  # For the first file
            else:
                base_docsearch.merge_from(docsearch)  # Merge subsequent indexes

        if base_docsearch:
            base_docsearch.save_local(f"faiss_index_{session_var}") 
            
            #cache.set(f"user_id_cache_{session['user_id']}", session['user_id'],timeout=0) #old cache based session storage
            
            cache.set(f"language_{session_var}", language,timeout=0)
            cache.set(f"prompt_{session_var}", prompt,timeout=0)
            end_time = time.time()
            execution_time = end_time - start_time
            minutes, seconds = divmod(execution_time, 60)
            formatted_time = f"{int(minutes):02}:{int(seconds):02}"
            execution_time_block = {"executionTime":f"{formatted_time}"}
            messageJson = '{"message": "Data processed!"}'
            response_with_time = json.loads(messageJson)
            response_with_time.update(execution_time_block)

            # Token uuid4 append
            token = jwt.encode({'uuid4': session_var,'exp': datetime.utcnow() + timedelta(days=7)}, app.secret_key, algorithm='HS256')
            response_with_time['token'] = token  # Add token as a string under the key 'token'

            logger.info(f"{json.dumps(response_with_time)}")
            return Response(json.dumps(response_with_time), mimetype='application/json')

    else:
        f = None
        filename = None
        logger.error("None")

    logger.critical("Unexpected Fault or Interruption")
    logger.critical(traceback.format_exc())
    # Return the processed text in JSON format
    # return jsonify({"response": response['text']})
    return jsonify(error="Unexpected Fault or Interruption")


@app.route("/process_data_without_file", methods=["GET", "POST"])
def process_data_without_file():
    try:
        prompt = request.args.get('prompt')
        language = request.args.get('language') # Already checked security in process_data route
        session_var = request.args.get('session_var')
        start_time = request.args.get('start_time')
        noFile = "1"

        cache.set(f"language_{session_var}", language,timeout=0)
        cache.set(f"prompt_{session_var}", prompt,timeout=0)
        cache.set(f"noFile_{session_var}", noFile,timeout=0)
        end_time = time.time()
        execution_time = end_time - float(start_time)
        minutes, seconds = divmod(execution_time, 60)
        formatted_time = f"{int(minutes):02}:{int(seconds):02}"
        execution_time_block = {"executionTime":f"{formatted_time}"}
        messageJson = '{"message": "Data processed!"}'
        response_with_time = json.loads(messageJson)
        response_with_time.update(execution_time_block)

        # Token uuid4 append
        token = jwt.encode({'uuid4': session_var,'exp': datetime.utcnow() + timedelta(days=7)}, app.secret_key, algorithm='HS256')
        response_with_time['token'] = token  # Add token as a string under the key 'token'

        logger.info(f"{json.dumps(response_with_time)}")
        return Response(json.dumps(response_with_time), mimetype='application/json')
    

    except Exception as e:
        logger.critical("Unexpected Fault or Interruption")
        logger.critical(traceback.format_exc())
        return jsonify(error=f"Unexpected Fault or Interruption: {str(e)}")


@app.route("/decide", methods=["GET", "POST"])
@token_required
def decide():

    user_id = g.user_uuid
    
    if request.method == 'POST':
        scenario = request.form.get('scenario')
        logger.info(f"Scenario type:{scenario}")

        model_type = request.args.get('model', 'azure') # to set default model
        model_name = request.args.get('modelName', 'gpt') # to set default model name
        model_local_embed = request.args.get('localEmbed', 'no') # to set default model state

        start_time = time.time() # Timer starts at the Post

        if scenario:

            prompt = cache.get(f"prompt_{user_id}")
            logger.info(f"Prompt loaded!:{prompt}")
            language = cache.get(f"language_{user_id}")
            logger.info(f"language:{language}")
            noFile = cache.get(f"noFile_{user_id}")
            logger.info(f"noFile:{noFile}")
                
            if noFile=="1":
                return redirect(url_for("decide_without_file", model_name=model_name, model_type=model_type, scenario=scenario))

            try:
                if model_type == "gemini"  and model_local_embed=='no':
                    # llm = ChatLiteLLM(model=f"gemini/{model_name}", temperature=0)
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=0)
                    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

                elif model_type == "azure" and model_local_embed=='no':
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-ada-002")


                logger.info(f"LLM is :: {llm}\n embedding is :: {embeddings}\n")

                load_docsearch = FAISS.load_local(f"faiss_index_{user_id}",embeddings, allow_dangerous_deserialization=True)

                response_LO_CA = LCD.PRODUCE_LEARNING_OBJ_COURSE(prompt, load_docsearch, llm, model_type, language)


                cache.set(f"scenario_{user_id}", scenario,timeout=0)
                end_time = time.time()
                execution_time = end_time - start_time
                minutes, seconds = divmod(execution_time, 60)
                formatted_time = f"{int(minutes):02}:{int(seconds):02}"
                execution_time_block = {"executionTime":f"{formatted_time}"}
                logger.info(f"{response_LO_CA.content}")
                response_with_time = json.loads(response_LO_CA.content) 
                response_with_time.update(execution_time_block)
                logger.info(f"{json.dumps(response_with_time)}")

                # Strategic placement of image removal is placed so less time taking route is used
                output_path = f"./imagefolder_{user_id}"
                LCD.REMOVE_DUP_IMG(output_path) #removes duplicate images extracted in process_data route

                return Response(json.dumps(response_with_time), mimetype='application/json')
                # return jsonify(response_LO_CA['text'])       

            except Exception as e:
                logger.error(f"An error occurred or abrupt Model change: {str(e)}")
                logger.error(traceback.format_exc())
                return jsonify(error=f"An error occurred or abrupt Model change: {str(e)}")

        else:
            logger.error("None")
        
        logger.critical("Unexpected Fault or Interruption")
        return jsonify(error="Unexpected Fault or Interruption")
    

@app.route("/decide_without_file", methods=["GET", "POST"])
@token_required
def decide_without_file():
    start_time = time.time()
    user_id = g.user_uuid
    try:
        prompt = cache.get(f"prompt_{user_id}")
        language = cache.get(f"language_{user_id}")

        model_name = request.args.get('model_name')
        model_type = request.args.get('model_type')
        scenario = request.args.get('scenario')

        if model_type == "gemini":
            # llm = ChatLiteLLM(model=f"gemini/{model_name}", temperature=0)
            llm = ChatGoogleGenerativeAI(model=model_name,temperature=0)

        elif model_type == "azure":
            llm = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"))


        response_LO_CA = LCD.PRODUCE_LEARNING_OBJ_COURSE_WITHOUT_FILE(prompt, llm, model_type, language)

        cache.set(f"scenario_{user_id}", scenario,timeout=0)
        end_time = time.time()
        execution_time = end_time - start_time
        minutes, seconds = divmod(execution_time, 60)
        formatted_time = f"{int(minutes):02}:{int(seconds):02}"
        execution_time_block = {"executionTime":f"{formatted_time}"}
        logger.info(f"{response_LO_CA.content}")
        response_with_time = json.loads(response_LO_CA.content) 
        response_with_time.update(execution_time_block)
        logger.info(f"{json.dumps(response_with_time)}")
    
        return Response(json.dumps(response_with_time), mimetype='application/json')

    except Exception as e:
        logger.critical("Unexpected Fault or Interruption")
        logger.critical(traceback.format_exc())
        return jsonify(error=f"Unexpected Fault or Interruption: {str(e)}")

def is_json_parseable(json_string):
    try:
        json_object = json.loads(json_string)
    except ValueError as e:
        return False, str(e)
    return True, json_object

@app.route("/generate_course", methods=["GET", "POST"])
@token_required
def generate_course():

    user_id = g.user_uuid
    if request.method == 'POST':
        learning_obj = request.form.get("learning_obj")
        cache.set(f"learning_obj_{user_id}", learning_obj, timeout=0)
        content_areas = request.form.get("content_areas")
        cache.set(f"content_areas_{user_id}", content_areas, timeout=0)

        model_type = request.args.get('model', 'azure') # to set default model
        model_name = request.args.get('modelName', 'gpt') # to set default model name
        model_local_embed = request.args.get('localEmbed', 'no') # to set default model state
        summarize_images = request.args.get('summarizeImages', 'on') # to set default value name
        temp = request.args.get('temp','0.1')
        logger.info(f"temp selected!: {temp}")

        # the mpv is declared two times in "argument" and then "form" getting sequence. So, if user using form
        # sets a value, the mpv of the form variable will priortize over the argument value
        mpv = None
        if request.form.get("mpv") is not None:
            mpv = request.form.get("mpv")
        else:
            mpv = request.args.get('mpv', '2') # to set default value to balanced mpv
        logger.info(f"mpv is: {mpv}")
        if mpv is not None:
            mpv = int(mpv)  # Convert mpv to an integer
            if not (0 <= mpv <= 4):
                return jsonify(error="mpv value should be between min 0 and max 4")

        noFile = cache.get(f"noFile_{user_id}")
        logger.info(f"starting generate_course_without_file since noFile=={noFile}")            
        if noFile=="1":
            return redirect(url_for("generate_course_without_file", model_name=model_name, model_type=model_type, temp=temp, mpv=mpv))

        start_route_time = time.time() # Timer starts at the Post

        if learning_obj and content_areas:

            prompt = cache.get(f"prompt_{user_id}")
            logger.info(f"Prompt loaded!: {prompt}")

            scenario = cache.get(f"scenario_{user_id}")
            logger.info(f"scenario loaded!: {scenario}")

            language = cache.get(f"language_{user_id}")
            logger.info(f"Language selected is: {language}")

            try:
                if model_type == 'gemini' and model_local_embed=='no':
                    # llm = ChatLiteLLM(model=f"gemini/{model_name}", temperature=float(temp)) # temp default 0.1
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=float(temp)) # temp default 0.1
                    # llm_img_summary = ChatLiteLLM(model=f"gemini/{model_name}",temperature=0)
                    llm_img_summary = ChatGoogleGenerativeAI(model=model_name,temperature=0)
                    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

                elif model_type == 'azure' and model_local_embed=='no':
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=float(temp),
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    llm_img_summary = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-ada-002")


                load_docsearch = FAISS.load_local(f"faiss_index_{user_id}",embeddings, allow_dangerous_deserialization=True)
                combined_prompt = f"{prompt}\n{learning_obj}\n{content_areas}"
                output_path = f"./imagefolder_{user_id}"

                start_RE_SIMILARITY_SEARCH_time = time.time()
                docs_main = LCD.RE_SIMILARITY_SEARCH(combined_prompt, load_docsearch, output_path, model_type,model_name, summarize_images, language, llm_img_summary)
                end_RE_SIMILARITY_SEARCH_time = time.time()
                execution_RE_SIMILARITY_SEARCH_time = end_RE_SIMILARITY_SEARCH_time - start_RE_SIMILARITY_SEARCH_time
                minutes, seconds = divmod(execution_RE_SIMILARITY_SEARCH_time, 60)
                formatted_RE_SIMILARITY_SEARCH_time = f"{int(minutes):02}:{int(seconds):02} with summarize_images switched = {summarize_images} " # for docs retreival and image summarizer

                logger.info(f"2nd Docs_main:\n{docs_main}")
                logger.info(f"combined_prompt\n{combined_prompt}")
            # doc_main has all the unfiltered meta image summaries appended with and not in vectorstore, however...
            # ... it has been list of images are chosen to be atleast reletive to the topic at hand
                
                start_TALK_WITH_RAG_time = time.time()


                response, scenario = LCD.TALK_WITH_RAG(scenario, content_areas, learning_obj, prompt, docs_main, llm, model_type, model_name,embeddings, language, mpv)
                
                end_TALK_WITH_RAG_time = time.time()
                execution_TALK_WITH_RAG_time = end_TALK_WITH_RAG_time - start_TALK_WITH_RAG_time
                minutes, seconds = divmod(execution_TALK_WITH_RAG_time, 60)
                formatted_TALK_WITH_RAG_time = f"{int(minutes):02}:{int(seconds):02}" # for docs JSON scenario response

                original_txt = response

                validity, result = is_json_parseable(original_txt)

                if validity == True:
                    start_REPAIR_SHADOW_EDGES_time = time.time()

                    response = LCD.REPAIR_SHADOW_EDGES(scenario, original_txt, model_type, model_name, language, mpv)
                    
                    end_REPAIR_SHADOW_EDGES_time = time.time()
                    execution_REPAIR_SHADOW_EDGES_time = end_REPAIR_SHADOW_EDGES_time - start_REPAIR_SHADOW_EDGES_time
                    minutes, seconds = divmod(execution_REPAIR_SHADOW_EDGES_time, 60)
                    formatted_REPAIR_SHADOW_EDGES_time = f"{int(minutes):02}:{int(seconds):02}" 

                else:
                    logger.error("JSON of original_txt is NOT VALID")
                    return jsonify(error="Failed to complete the scenario")
                
                cache.set(f"docs_main_{user_id}", docs_main, timeout=0)
                cache.set(f"response_text_{user_id}", response, timeout=0)

                end_route_time = time.time()
                execution_route_time = end_route_time - start_route_time
                minutes, seconds = divmod(execution_route_time, 60)
                formatted_route_time = f"{int(minutes):02}:{int(seconds):02}"

                execution_time_block = {"executionTime":f"""For whole Route is {formatted_route_time};\nFor document retreival &/or image summarizer is {formatted_RE_SIMILARITY_SEARCH_time};\nFor JSON scenario response is {formatted_TALK_WITH_RAG_time};\nFor Shadow Edges Repair is {formatted_REPAIR_SHADOW_EDGES_time}"""}
                response_with_time = json.loads(response) 
                response_with_time.update(execution_time_block)

                logger.info(f"{json.dumps(response_with_time, indent=4)}")
                return Response(json.dumps(response_with_time), mimetype='application/json')
                # return jsonify(message=f"""{response}""")
            except Exception as e:
                logger.error(f"An error occurred or abrupt Model change: {str(e)}")
                logger.error(traceback.format_exc())
                return jsonify(error=f"An error occurred or abrupt Model change: {str(e)}")

        else:
            logger.error("None")
        
        logger.critical("Unexpected Fault or Interruption")
        return jsonify(error="Unexpected Fault or Interruption")


@app.route("/generate_course_without_file", methods=["GET", "POST"])
@token_required
def generate_course_without_file():
    start_time = time.time()
    user_id = g.user_uuid
    try:
        model_name = request.args.get('model_name')
        model_type = request.args.get('model_type')
        temp = request.args.get('temp')
        mpv = request.args.get('mpv')

        learning_obj = cache.get(f"learning_obj_{user_id}")
        logger.info(f"learning_obj!: {learning_obj}")
        content_areas = cache.get(f"content_areas_{user_id}")
        logger.info(f"content_areas!: {content_areas}")
        
        repair_shadows_without_file = "1" # For onwards use in shadow edges repair function to seperate the file prompts and without-file prompts

        prompt = cache.get(f"prompt_{user_id}")
        logger.info(f"Prompt loaded!: {prompt}")

        scenario = cache.get(f"scenario_{user_id}")
        logger.info(f"scenario loaded!: {scenario}")

        language = cache.get(f"language_{user_id}")
        logger.info(f"Language selected is: {language}")

        if model_type == "gemini":
            # llm = ChatLiteLLM(model=f"gemini/{model_name}",temperature=float(temp))
            llm = ChatGoogleGenerativeAI(model=model_name,temperature=float(temp))

        elif model_type == "azure":
            llm = AzureChatOpenAI(deployment_name=model_name, temperature=float(temp),
                                openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"))
            
        response = LCD.TALK_WITH_RAG_WITHOUT_FILE(scenario, content_areas, learning_obj, prompt, llm, model_type, model_name, language, mpv)

        original_txt = response

        validity, result = is_json_parseable(original_txt)

        if validity == True:
            response = LCD.REPAIR_SHADOW_EDGES(scenario, original_txt, model_type, model_name, language, mpv, repair_shadows_without_file)
        else:
            logger.error("JSON of original_txt is NOT VALID")
            return jsonify(error="Failed to complete the scenario. JSON is NOT VALID")


        end_time = time.time()
        execution_route_time = end_time - start_time
        minutes, seconds = divmod(execution_route_time, 60)
        formatted_route_time = f"{int(minutes):02}:{int(seconds):02}"

        execution_time_block = {"executionTime":f"{formatted_route_time}"}
        response_with_time = json.loads(response) 
        response_with_time.update(execution_time_block)

        logger.info(f"{json.dumps(response_with_time, indent=4)}")
        return Response(json.dumps(response_with_time), mimetype='application/json')
    
    except Exception as e:
        logger.critical("Unexpected Fault or Interruption")
        logger.critical(traceback.format_exc())
        return jsonify(error=f"Unexpected Fault or Interruption: {str(e)}")

@app.route("/find_images", methods=["GET", "POST"])
@token_required
def find_images():
    user_id = g.user_uuid
    if request.method == 'POST':
        model_type = request.args.get('model', 'azure') # default select openai
        model_name = request.args.get('modelName', 'gpt') # to set default model name
        
        response_text = cache.get(f"response_text_{user_id}")
        docs_main = cache.get(f"docs_main_{user_id}")
        output_path = f"./imagefolder_{user_id}"

        language = cache.get(f"language_{user_id}")
        logger.info(f"Language seleted is:{language}")

        start_route_time = time.time() # Timer starts at the Post

        if response_text and docs_main:
            try:
                if model_type == "gemini":
                    # llm = ChatLiteLLM(model=f"gemini/{model_name}",temperature=0.1)
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=0.1)
                else:
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=0.1,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )

                img_response = LCD.ANSWER_IMG(response_text, llm,docs_main,language,model_type)

                json_img_response = json.loads(img_response)
                logger.info(f"""json_img_response is:: {str(json_img_response)}""")

                def encode_image(image_path):
                    with open(image_path, "rb") as f:
                        return base64.b64encode(f.read()).decode('utf-8')
                    
                
                image_elements = []
                for key, value in json_img_response.items():
                    if 'Image' in key:  # This ensures we're only dealing with image keys
                        normalized_value = value.lower()  # Normalize as filenames may vary
                        matched = False
                        for imgfolder in os.listdir(output_path):
                            logger.info(f"Image folder is ::{imgfolder}")
                            imgfolder = os.path.join(output_path, imgfolder)
                            for image_file in os.listdir(imgfolder):
                                logger.info(f"Image file is::{image_file}")
                                if image_file.endswith(('.png', '.jpg', '.jpeg', '.webp', '.JPG')):
                                    # rsplit to remove extensions and make string in lower-case
                                    image_file_without_extension = image_file.rsplit('.', 1)[0].lower()
                                    normalized_value = normalized_value.rsplit('.', 1)[0].lower()

                                    if normalized_value in image_file_without_extension and "pixmapped" not in image_file_without_extension:  # Case insensitive comparison
                                        image_path = os.path.join(imgfolder, image_file)
                                        encoded_image = encode_image(image_path)
                                        image_elements.append(encoded_image)
                                        matched = True
                                        break  # Stop searching once a match is found for this key
                            if not matched:
                                logger.info(f"No match found for: {normalized_value}")
                
                count_var = 0
                for r in image_elements:
                    count_var += 1
                    json_img_response[f"base64_Image{count_var}"] = r
                    logger.info(f"""{str(json_img_response)}""")

                # logic to delete NOT RELEVANT keys

                keys_to_remove = []

                # Iterate through the Logic keys to identify the ones to remove
                logic_count = 1
                while f'Logic{logic_count}' in json_img_response:
                    logic_key = f'Logic{logic_count}'
                    if json_img_response[logic_key] == "NOT RELEVANT":
                        description_key = f'Description{logic_count}'
                        base_key = f'base64_Image{logic_count}'
                        image_key = f'Image{logic_count}'
                        keys_to_remove.extend([logic_key, description_key, base_key, image_key])
                    logic_count += 1

                # Remove the identified keys from the dictionary
                for key in keys_to_remove:
                    if key in json_img_response:
                        del json_img_response[key]

                logger.info(f"Type of json_img_response:{type(json_img_response)}") 

                end_route_time = time.time()
                execution_route_time = end_route_time - start_route_time
                minutes, seconds = divmod(execution_route_time, 60)
                formatted_route_time = f"{int(minutes):02}:{int(seconds):02}"

                execution_time_block = {"executionTime":f"""For whole Route is {formatted_route_time}"""}
                json_img_response.update(execution_time_block) # already type dict json_img_response

                logger.info(f"{json.dumps(json_img_response, indent=4)}") # for indentational debug

                return jsonify(json_img_response) #This one works
            except Exception as e:
                logger.error(f"An error occurred or abrupt Model change: {str(e)}")
                logger.error(traceback.format_exc())
                return jsonify(error=f"An error occurred or abrupt Model change: {str(e)}")


            # shutil.rmtree(f"faiss_index_{user_id_cache}")

            # shutil.rmtree(output_path) #images store folder
            # cache.delete(f"response_text_{user_id_cache}")
            # cache.delete(f"prompt_{user_id_cache}")
            # cache.delete(f"scenario_{user_id_cache}")
            # cache.delete("user_id_cache")

        else:
            logger.error("response_text and docs_main most likely NOT FOUND")
        
        logger.critical("Unexpected Fault or Interruption")
        return jsonify(error="Unexpected Fault or Interruption")
        

if __name__ == '__main__': # runs in local deployment only, and NOT in docker since CMD command takes care of it

    try:
        app.run(use_reloader=False)  # use_reloader=False to avoid duplicate jobs
        # for runing the app with eventlet WSGI server
        # http_server = WSGIServer(("127.0.0.1", 5000), app)
        # http_server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
