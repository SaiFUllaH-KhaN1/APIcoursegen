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
import urllib.request
from urllib.parse import urlparse, urljoin

from transformers import pipeline, WhisperProcessor, WhisperForConditionalGeneration
from langchain_community.embeddings import HuggingFaceBgeEmbeddings

load_dotenv(dotenv_path="HUGGINGFACEHUB_API_TOKEN.env")

openai.api_type = os.getenv("OPENAI_API_TYPE")
openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# Configuration for the cache directory
cache_dir = 'cache'

# Check if the cache directory exists, and create it if it does not
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
    logger.debug(f"Cache directory '{cache_dir}' was created.")
else:
    logger.debug(f"Cache directory '{cache_dir}' already exists.")

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
    r"/decide": {"origins": allowed_origins},
    r"/generate_course": {"origins": allowed_origins},
     r"/find_images": {"origins": allowed_origins}
})

### TOKEN DECORATORS ###
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Extract the token from the Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or 'Bearer ' not in auth_header:
            logger.critical("message: Missing or malformed token")
            return jsonify({"message": "Missing or malformed token"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            # Decode the token using PyJWT's built-in expiration verification
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            # Extract uuid4 from the decoded token
            g.user_uuid = decoded['uuid4']
            logger.debug(f"Token Decoded Success!:{g.user_uuid}") # NOT FOR PRODUCTION

        except jwt.ExpiredSignatureError:
            logger.critical("message: Token has expired")
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            logger.critical("message: Invalid token")
            return jsonify({"message": "Invalid token"}), 401
        except Exception as e:
            # Catch other exceptions, such as no 'uuid4' in token
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
            logger.debug(f"Deleting Faiss directory: {dir_path}")
            shutil.rmtree(dir_path)
        elif os.path.isdir(dir_path) and item.startswith("imagefolder_"):
            logger.debug(f"Deleting image directory: {dir_path}")
            shutil.rmtree(dir_path)
        elif os.path.isdir(dir_path) and item.startswith("audio_"):
            logger.debug(f"Deleting audio directory: {dir_path}")
            shutil.rmtree(dir_path)

@app.route("/cron", methods=['POST'])
@basic_auth.required
def cron():
    delete_indexes()
    logger.debug("Deleted FAISS index")
    return jsonify(message="FAISS and imagefolder and audio index directories deleted")
###     ###     ### 

### SCHEDULED DELETION OF folders of imagefolder_ and faiss_index_ ###
def delete_old_directories():
    time_to_delete_files_older_than = timedelta(hours=6)
    logger.debug(f"Scheduler is running the delete_old_directories function to delete files older than {time_to_delete_files_older_than}.")
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    for item in os.listdir(base_path):
        dir_path = os.path.join(base_path, item)
        if os.path.isdir(dir_path) and item.startswith("faiss_index_") or item.startswith("imagefolder_") or item.startswith("audio_"):
            # Check if directory is older than a specified time
            dir_age = datetime.fromtimestamp(os.path.getmtime(dir_path))
            if datetime.now() - dir_age > time_to_delete_files_older_than:
                logger.debug(f"Deleting directory: {dir_path}, it has modified date of {dir_age}")
                shutil.rmtree(dir_path)
###     ###     ###

### WHISPER START

# Configuration for the audio directory
audio_dir = 'audio_files'
# Check if the cache directory exists, and create it if it does not
if not os.path.exists(audio_dir):
    os.makedirs(audio_dir)
    logger.debug(f"Audio directory '{audio_dir}' was created.")
else:
    logger.debug(f"Audio directory '{audio_dir}' already exists.")


### MODEL CHECK ALREADY DOWNLOADED ?
global whisper_model
whisper_model = "whisper-base" # Change this line only if a new different model download wanted 
# for production use whisper-base. Only tiny model for local checking 

def download_whisper_model(whisper_model):
    global whisper  # Ensure we are modifying the global whisper variable
    whisper = None
    global whisper_directory 
    whisper_directory = f"./whisper_local/{whisper_model}"

    # Check if the model directory exists
    if not os.path.exists(whisper_directory):
        logger.debug("Downloading Whisper model...")
        model = WhisperForConditionalGeneration.from_pretrained(f"openai/{whisper_model}", cache_dir=whisper_directory)
        processor = WhisperProcessor.from_pretrained(f"openai/{whisper_model}", cache_dir=whisper_directory)
        logger.debug("Model downloaded successfully!")
    else:
        logger.debug("Whisper Tiny model already downloaded. Skipping download.")
        pass

# Calling function
download_whisper_model(whisper_model)

### WHSIPER END


### EMBED MODEL START
global embed_model
embed_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

def download_Embed_model(embed_model):
    
    global embed_directory
    embed_directory = f"./embed_local/{embed_model}"

    # Check if the model directory exists
    if not os.path.exists(embed_directory):
        logger.debug("Downloading Embed model...")

        embeddings = HuggingFaceBgeEmbeddings(
            model_name= embed_model,
            cache_folder = embed_directory,
            model_kwargs={'device': 'cpu', "trust_remote_code": True},
            encode_kwargs={'normalize_embeddings': True}
        )
        logger.debug("Model downloaded successfully!")
    else:
        logger.debug("Embed model already downloaded. Skipping download.")
        pass

# Call the download function at the start of your application
download_Embed_model(embed_model)

### EMBED MODEL END


@app.route("/process_data", methods=["GET", "POST"])
def process_data():

    if request.method == 'POST':
        start_time = time.time() # Timer starts at the Post

        # Create a unique session user_id if not exists
        session_var = str(uuid.uuid4())
        output_path = f"./imagefolder_{session_var}"
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
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
            logger.debug(f"user_agent alternate: {user_agents}")
        else:
            logger.debug(f"user_agent from client: {user_agents}")

        
        prompt = request.form.get("prompt")
        url_doc = request.form.get('url_doc')
        f = request.files.getlist('file')
        logger.debug("There is a File")

        language = request.form.get("language","english").lower()
        allowed_languages = ["english","finnish","spanish","german","italian","french"]

        if language not in allowed_languages:
            logger.error("Invalid Language Selected. Select out of english,finnish,spanish,german,italian or french.")
            return jsonify(error="Invalid Language Selected. Select out of english,finnish,spanish,german,italian or french.")
        else:
            logger.debug(f"Language Selected is:{language}")


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
                    pdf_file_wrapper = FileStorage(stream=pdf_bytes, filename=f'extracted_content{session_var}.pdf', content_type='application/pdf') #still not unique for the same session so either url or youtube url processed at the same time
                    pdf_file_wrapper.seek(0)
                    f.append(pdf_file_wrapper)
                
            else:
                def fetch_url(url):
                    for user_agent in user_agents:
                        headers = {'User-Agent': user_agent}
                        request = urllib.request.Request(url, headers=headers)
                        
                        try:
                            response = urllib.request.urlopen(request, timeout=3)
                            soup = BeautifulSoup(response.read(), 'html.parser')
                            var = soup.get_text()
                            logger.debug(f"Extracted text length: {len(var)}")
                            return  var, soup
                        except (HTTPError, URLError) as e:
                            logger.debug(f"Error with {user_agent}: {str(e)}")
                            continue  # Try the next user agent in case of an error

                # Test the function with a given URL
                var, soup = fetch_url(url_doc)

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

        filename = [f_name.filename for f_name in f]
        logger.debug(f"Filename is::{filename}")

        base_docsearch = None
        for file in f:

            ### ONLY FOR AUDIO CHECK ###
            filename = file.filename
            logger.debug("filename is",filename)
            extension = filename.rsplit('.', 1)[1].lower()
            temp_path_audio = os.path.join(audio_dir, f"audio_{session_var}_{filename}")
            if extension =="mp3":
                logger.debug("temp_path_audio",temp_path_audio)
                file.save(temp_path_audio)
            ## AUDIO CHECK END    

            file_content = io.BytesIO(file.read())
            # file_content = [io.BytesIO(fs.read()) for fs in f]
            logger.debug("LCD initiated!")
            try:
                if model_type == 'gemini' and model_local_embed == 'no':
                    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001" )
                elif model_type == 'azure' and model_local_embed == 'no':
                    embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-ada-002")
                elif model_local_embed=='yes':
                    embeddings = HuggingFaceBgeEmbeddings(
                        model_name= embed_model,
                        cache_folder = embed_directory,
                        model_kwargs={'device': 'cpu', "trust_remote_code": True},
                        encode_kwargs={'normalize_embeddings': True}
                    )
                logger.debug(f"Using embeddings of {embeddings}")
                docsearch = LCD.RAG(file_content,embeddings,file,session_var, temp_path_audio,filename, extension, whisper_directory, whisper_model, language)
            except Exception as e:
                docsearch = None
                logger.error(f"Error processing file:{str(e)}")
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

            logger.debug(f"{json.dumps(response_with_time)}")
            return Response(json.dumps(response_with_time), mimetype='application/json')

    else:
        f = None
        filename = None
        logger.error("None")

    logger.critical("Unexpected Fault or Interruption")

    # Return the processed text in JSON format
    # return jsonify({"response": response['text']})
    return jsonify(error="Unexpected Fault or Interruption")

@app.route("/decide", methods=["GET", "POST"])
@token_required
def decide():

    user_id = g.user_uuid
    if request.method == 'POST':
        scenario = request.form.get('scenario')
        logger.debug(f"Scenario type:{scenario}")

        model_type = request.args.get('model', 'azure') # to set default model
        model_name = request.args.get('modelName', 'gpt') # to set default model name
        model_local_embed = request.args.get('localEmbed', 'no') # to set default model state

        start_time = time.time() # Timer starts at the Post

        if scenario:

            prompt = cache.get(f"prompt_{user_id}")
            language = cache.get(f"language_{user_id}")
            logger.debug(f"Prompt loaded!:{prompt}")

            try:
                if model_type == "gemini"  and model_local_embed=='no':
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=0)
                    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

                elif model_type == "azure" and model_local_embed=='no':
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-ada-002")

                elif model_type == "gemini"  and  model_local_embed=='yes':
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=0)
                    embeddings = HuggingFaceBgeEmbeddings(
                        model_name= embed_model,
                        cache_folder = embed_directory,
                        model_kwargs={'device': 'cpu', "trust_remote_code": True},
                        encode_kwargs={'normalize_embeddings': True}
                    )

                elif model_type == "azure"  and  model_local_embed=='yes':
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    embeddings = HuggingFaceBgeEmbeddings(
                        model_name= embed_model,
                        cache_folder = embed_directory,
                        model_kwargs={'device': 'cpu', "trust_remote_code": True},
                        encode_kwargs={'normalize_embeddings': True}
                    )


                logger.debug(f"LLM is :: {llm}\n embedding is :: {embeddings}\n")
                
                load_docsearch = FAISS.load_local(f"faiss_index_{user_id}",embeddings,allow_dangerous_deserialization=True)
                
                chain, docs_main, query = LCD.PRODUCE_LEARNING_OBJ_COURSE(prompt, load_docsearch, llm, model_type)
                logger.debug(f"1st Docs_main of /Decide route:{docs_main}")

                logger.debug("response_LO_CA started")
                response_LO_CA = chain({"input_documents": docs_main,"human_input": query, "language":language})
                logger.debug(f"{response_LO_CA}")
                logger.debug("response_LO_CA ended")

                cache.set(f"scenario_{user_id}", scenario,timeout=0)
                end_time = time.time()
                execution_time = end_time - start_time
                minutes, seconds = divmod(execution_time, 60)
                formatted_time = f"{int(minutes):02}:{int(seconds):02}"
                execution_time_block = {"executionTime":f"{formatted_time}"}
                logger.debug(f"{response_LO_CA['text']}")
                response_with_time = json.loads(response_LO_CA['text']) 
                response_with_time.update(execution_time_block)
                logger.debug(f"{json.dumps(response_with_time)}")

                # Strategic placement of image removal is placed so less time taking route is used
                output_path = f"./imagefolder_{user_id}"
                LCD.REMOVE_DUP_IMG(output_path) #removes duplicate images extracted in process_data route

                return Response(json.dumps(response_with_time), mimetype='application/json')
                # return jsonify(response_LO_CA['text'])       

            except Exception as e:
                logger.error(f"An error occurred or abrupt Model change: {str(e)}")
                return jsonify(error=f"An error occurred or abrupt Model change: {str(e)}")

        else:
            logger.error("None")
        
        logger.critical("Unexpected Fault or Interruption")
        return jsonify(error="Unexpected Fault or Interruption")
    
@app.route("/generate_course", methods=["GET", "POST"])
@token_required
def generate_course():

    def is_json_parseable(json_string):
        try:
            json_object = json.loads(json_string)
        except ValueError as e:
            return False, str(e)
        return True, json_object

    user_id = g.user_uuid
    if request.method == 'POST':
        learning_obj = request.form.get("learning_obj")
        content_areas = request.form.get("content_areas")

        model_type = request.args.get('model', 'azure') # to set default model
        model_name = request.args.get('modelName', 'gpt') # to set default model name
        model_local_embed = request.args.get('localEmbed', 'no') # to set default model state
        summarize_images = request.args.get('summarizeImages', 'on') # to set default value name
        temp = request.args.get('temp','0.1')
        logger.debug(f"temp selected!: {temp}")
        
        start_route_time = time.time() # Timer starts at the Post

        if learning_obj and content_areas:

            prompt = cache.get(f"prompt_{user_id}")
            logger.debug(f"Prompt loaded!: {prompt}")

            scenario = cache.get(f"scenario_{user_id}")
            logger.debug(f"scenario loaded!: {scenario}")

            language = cache.get(f"language_{user_id}")
            logger.debug(f"Language selected is: {language}")

            try:
                if model_type == 'gemini' and model_local_embed=='no':
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=temp, max_output_tokens=8000) # temp default 0.1
                    llm_img_summary = ChatGoogleGenerativeAI(model=model_name,temperature=0)
                    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

                elif model_type == 'azure' and model_local_embed=='no':
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=temp,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    llm_img_summary = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-ada-002")

                elif model_type == 'gemini' and model_local_embed=='yes':
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=temp, max_output_tokens=8000) # temp default 0.1
                    llm_img_summary = ChatGoogleGenerativeAI(model=model_name,temperature=0)
                    embeddings = HuggingFaceBgeEmbeddings(
                        model_name= embed_model,
                        cache_folder = embed_directory,
                        model_kwargs={'device': 'cpu', "trust_remote_code": True},
                        encode_kwargs={'normalize_embeddings': True}
                    )

                elif model_type == 'azure' and model_local_embed=='yes':
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=temp,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    llm_img_summary = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
                    embeddings = HuggingFaceBgeEmbeddings(
                        model_name= embed_model,
                        cache_folder = embed_directory,
                        model_kwargs={'device': 'cpu', "trust_remote_code": True},
                        encode_kwargs={'normalize_embeddings': True}
                    )

                load_docsearch = FAISS.load_local(f"faiss_index_{user_id}",embeddings,allow_dangerous_deserialization=True)
                combined_prompt = f"{prompt}\n{learning_obj}\n{content_areas}"
                output_path = f"./imagefolder_{user_id}"

                start_RE_SIMILARITY_SEARCH_time = time.time()
                docs_main = LCD.RE_SIMILARITY_SEARCH(combined_prompt, load_docsearch, output_path, model_type,model_name, summarize_images, language, llm_img_summary)
                end_RE_SIMILARITY_SEARCH_time = time.time()
                execution_RE_SIMILARITY_SEARCH_time = end_RE_SIMILARITY_SEARCH_time - start_RE_SIMILARITY_SEARCH_time
                minutes, seconds = divmod(execution_RE_SIMILARITY_SEARCH_time, 60)
                formatted_RE_SIMILARITY_SEARCH_time = f"{int(minutes):02}:{int(seconds):02} with summarize_images switched = {summarize_images} " # for docs retreival and image summarizer

                logger.debug(f"2nd Docs_main:\n{docs_main}")
                logger.debug(f"combined_prompt\n{combined_prompt}")
            # doc_main has all the unfiltered meta image summaries appended with and not in vectorstore, however...
            # ... it has been list of images are chosen to be atleast reletive to the topic at hand
                
                start_TALK_WITH_RAG_time = time.time()


                response, scenario = LCD.TALK_WITH_RAG(scenario, content_areas, learning_obj, prompt, docs_main, llm, model_type, model_name,embeddings, language)
                
                end_TALK_WITH_RAG_time = time.time()
                execution_TALK_WITH_RAG_time = end_TALK_WITH_RAG_time - start_TALK_WITH_RAG_time
                minutes, seconds = divmod(execution_TALK_WITH_RAG_time, 60)
                formatted_TALK_WITH_RAG_time = f"{int(minutes):02}:{int(seconds):02}" # for docs JSON scenario response

                original_txt = response

                validity, result = is_json_parseable(original_txt)

                if validity == True:
                    start_REPAIR_SHADOW_EDGES_time = time.time()

                    response = LCD.REPAIR_SHADOW_EDGES(scenario, original_txt, model_type, model_name, language)
                    
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

                logger.debug(f"{json.dumps(response_with_time, indent=4)}")
                return Response(json.dumps(response_with_time), mimetype='application/json')
                # return jsonify(message=f"""{response}""")
            except Exception as e:
                logger.error(f"An error occurred or abrupt Model change: {str(e)}")
                return jsonify(error=f"An error occurred or abrupt Model change: {str(e)}")

        else:
            logger.error("None")
        
        logger.critical("Unexpected Fault or Interruption")
        return jsonify(error="Unexpected Fault or Interruption")



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
        logger.debug(f"Language seleted is:{language}")

        start_route_time = time.time() # Timer starts at the Post

        if response_text and docs_main:
            try:
                if model_type == "gemini":
                    llm = ChatGoogleGenerativeAI(model=model_name,temperature=0.1)
                else:
                    llm = AzureChatOpenAI(deployment_name=model_name, temperature=0.1,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )

                img_response = LCD.ANSWER_IMG(response_text, llm,docs_main,language,model_type)

                json_img_response = json.loads(img_response)
                logger.debug(f"""json_img_response is:: {str(json_img_response)}""")

                def encode_image(image_path):
                    with open(image_path, "rb") as f:
                        return base64.b64encode(f.read()).decode('utf-8')
                    
                
                image_elements = []
                for key, value in json_img_response.items():
                    if 'Image' in key:  # This ensures we're only dealing with image keys
                        normalized_value = value.lower()  # Normalize as filenames may vary
                        matched = False
                        for imgfolder in os.listdir(output_path):
                            logger.debug(f"Image folder is ::{imgfolder}")
                            imgfolder = os.path.join(output_path, imgfolder)
                            for image_file in os.listdir(imgfolder):
                                logger.debug(f"Image file is::{image_file}")
                                if image_file.endswith(('.png', '.jpg', '.jpeg', '.webp', '.JPG')):
                                    if normalized_value in image_file.lower():  # Case insensitive comparison
                                        image_path = os.path.join(imgfolder, image_file)
                                        encoded_image = encode_image(image_path)  # Assuming you have a function `encode_image`
                                        image_elements.append(encoded_image)
                                        matched = True
                                        break  # Stop searching once a match is found for this key
                            if not matched:
                                logger.debug(f"No match found for: {value}")
                
                count_var = 0
                for r in image_elements:
                    count_var += 1
                    json_img_response[f"base64_Image{count_var}"] = r
                    logger.debug(f"""{str(json_img_response)}""")

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

                logger.debug(f"Type of json_img_response:{type(json_img_response)}") 

                end_route_time = time.time()
                execution_route_time = end_route_time - start_route_time
                minutes, seconds = divmod(execution_route_time, 60)
                formatted_route_time = f"{int(minutes):02}:{int(seconds):02}"

                execution_time_block = {"executionTime":f"""For whole Route is {formatted_route_time}"""}
                json_img_response.update(execution_time_block) # already type dict json_img_response

                logger.debug(f"{json.dumps(json_img_response, indent=4)}") # for indentational debug

                return jsonify(json_img_response) #This one works
            except Exception as e:
                logger.error(f"An error occurred or abrupt Model change: {str(e)}")
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
        
        
if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler.add_job(delete_old_directories, 'interval', hours=6)
    scheduler.start()

    try:
        app.run(use_reloader=False)  # use_reloader=False to avoid duplicate jobs
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
