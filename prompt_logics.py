# from langchain_openai import ChatOpenAI
import PROMPTS as PROMPTS
import logging
from langchain.chains import LLMChain
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
import base64
from langchain.schema.messages import HumanMessage, SystemMessage
# from PyPDF2 import PdfReader
from pypdf import PdfReader
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
import os
import shutil
import json
from langchain.schema.document import Document
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.document_loaders import UnstructuredExcelLoader, UnstructuredWordDocumentLoader, UnstructuredPowerPointLoader, TextLoader
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import List, Dict, Any, Optional
from docx2python import docx2python
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import shutil
import re
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from PIL import Image
from langchain.utils.math import cosine_similarity

# Logging Declaration
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logger = logging
logger.basicConfig(level= logging.DEBUG, format= log_format)

def RAG(file_content,embeddings,file,session_var):
    logger.debug(f"file is: {file}",)
    
    filename = file.filename
    logger.debug(filename)
    extension = filename.rsplit('.', 1)[1].lower()
    filename_without_extension = filename.rsplit('.', 1)[0].lower()
    output_path_byfile = f"./imagefolder_{session_var}/images_{session_var}_{filename_without_extension}"
    if not os.path.exists(output_path_byfile):
        os.makedirs(output_path_byfile) 
    logger.debug(f"Extension is: {extension}",)
    raw_text = ''
    texts = '' # for pdf image path only!
    if extension=="pdf":

        # For Image processing
        if f'extracted_content{session_var}.pdf' not in filename:
            pdf_reader = PdfReader(file_content)
            pgcount=0
            for i, page in enumerate(pdf_reader.pages):
                text_instant = page.extract_text()
                pgcount += 1
                imgcount = 1
                text_instant = f"\nThe Content of PageNumber:{pgcount} of file name:{filename_without_extension} is:\n{text_instant}.\nEnd of PageNumber:{pgcount} of file name:{filename_without_extension}\n"
                try:
                    for image_file_object in page.images:
                        # base_name = os.path.splitext(os.path.basename(image_file_object.name))[0]  # Get the base file name without extension
                        extension = os.path.splitext(image_file_object.name)[1]  # Get the file extension
                        base_name = f"FileName {filename_without_extension} PageNumber {pgcount} ImageNumber {imgcount}"  # Construct new file name with count
                        if extension == ".jp2":
                            logger.debug(f"Checking Image Extension {extension}",)
                            image_path = os.path.join(output_path_byfile, base_name)  # Construct the full output path
                            imgcount += 1
                            with open(image_path, "wb") as fp:
                                fp.write(image_file_object.data)
                            with Image.open(image_path) as im:
                                new_image_name = base_name + ".png"  # New image name for PNG
                                new_image_path = os.path.join(output_path_byfile, new_image_name)  # New full path for PNG
                                im.save(new_image_path)  # Save the image as PNG
                                os.remove(image_path)
                        else:
                            image_name = f"FileName {filename_without_extension} PageNumber {pgcount} ImageNumber {imgcount}{extension}"  # Construct new file name with count
                            image_path = os.path.join(output_path_byfile, image_name)  # Construct the full output path
                            imgcount += 1
                            with open(image_path, "wb") as fp:
                                fp.write(image_file_object.data)
                            with Image.open(image_path) as im:
                                if im.mode in ["P", "PA"]:
                                    logger.debug(f"Image of P or PA Mode detected:{im.mode}",)
                                    im = im.convert("RGBA")  # Convert palette-based images to RGBA
                                    new_image_name = base_name + ".png"  # New image name for PNG
                                    new_image_path = os.path.join(output_path_byfile, new_image_name)  # New full path for PNG
                                    im.save(new_image_path)  # Save the image as PNG
                                    os.remove(image_path)
                                else:
                                    pass
                        

                except Exception as e:
                    logger.debug(f"Error processing image {image_file_object.name}: {e}")
                    continue  # Skip to the next image
                if text_instant:
                    texts += text_instant
            # at this point we got text and images extracted, stored in ./images folder, lets summarize images

            # Get image summaries
            # image_elements = []
            # image_summaries = []
            # image_path = output_path_byfile

            # def encode_image(image_path):
            #     with open(image_path, "rb") as f:
            #         return base64.b64encode(f.read()).decode('utf-8')

            # def summarize_image(encoded_image, basename):
            #     prompt = [
            #         SystemMessage(content="You are a bot that is good at analyzing images."),
            #         HumanMessage(content=[
            #             {
            #                 "type": "text",
            #                 "text": f"Describe the contents of this image. Tell what FileName, PageNumber and ImageNumber of this image is by seeing this information: {basename}. Your output should look like this: 'This image that belongs to FileName: ..., PageNumber: ..., ImageNumber: .... In this Image ...'"
            #             },
            #             {
            #                 "type": "image_url",
            #                 "image_url": {
            #                     "url": f"data:image/jpeg;base64,{encoded_image}"
            #                 },
            #             },
            #         ])
            #     ]
            #     response = ChatOpenAI(model="gpt-4o", max_tokens=128).invoke(prompt)
            #     return response.content

            # for i in os.listdir(output_path_byfile):
            #     if i.endswith(('.png', '.jpg', '.jpeg')):
            #         image_path = os.path.join(output_path_byfile, i)
            #         basename = os.path.basename(image_path) 
            #         print(os.path.basename(image_path))
            #         encoded_image = encode_image(image_path)
            #         image_elements.append(encoded_image)
            #         summary = summarize_image(encoded_image,basename)
            #         image_summaries.append(summary)

            # print("Image Summary is::",image_summaries)

            # text_merged = texts + "\n" + str(image_summaries)
            # print(text_merged) # Will be used onwards to create the faiss_index text database
            
        else:
            logger.debug("We are processing for url or youtube's extracted_content.pdf")
            # Without the Image Processing
            doc_reader = PdfReader(file_content)

            for i, page in enumerate(doc_reader.pages):
                text = page.extract_text()

                if text:
                    raw_text += text

    elif extension=="csv":
        temp_path = os.path.join(f"{filename}{session_var}")
        file.seek(0)
        file.save(temp_path)
        loader = CSVLoader(file_path=temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content + '\n\n' for document in data)
        os.remove(temp_path)

    elif extension=="xlsx" or extension=="xls":
        temp_path = os.path.join(f"{filename}{session_var}")
        file.seek(0)
        file.save(temp_path)
        loader = UnstructuredExcelLoader(temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content + '\n\n' for document in data)
        os.remove(temp_path)

    elif extension=="docx":
        # temp_path = os.path.join(filename)
        # file.seek(0)
        # file.save(temp_path)
        # loader = UnstructuredWordDocumentLoader(temp_path)
        # data = loader.load()
        # raw_text = raw_text.join(document.page_content for document in data)
        # os.remove(temp_path)
        def extract_and_rename_images(docx_path, output_dir):
            # Extract the contents of the DOCX file
            content = docx2python(docx_path, extract_image=True,  image_folder=output_dir)
            logger.debug(content)
            # Flatten the list of lists containing the images
            images = content.images
            image_info = []
            for image_name in images.keys():
                base_name, ext = os.path.splitext(image_name)
                logger.debug(f"Base Name: {base_name}, Extension: {ext}")
                image_info.append((base_name, ext))
            # Rename images based on their location
            image_count = 1
            i = 0
            texts = ""
            for section_index, section in enumerate(content.body):
                for row_index, row in enumerate(section):
                    for cell_index, cell in enumerate(row):
                        for paragraph_index, paragraph in enumerate(cell):
                            if '----media/' in paragraph:
                                # Extract the image filename from the placeholder
                                start_index = paragraph.find('----media/') + len('----media/')
                                end_index = paragraph.find('----', start_index)
                                image_filename = paragraph[start_index:end_index]

                                # Construct the original image path
                                original_image_path = os.path.join(output_dir, image_filename)
                                # base_name = os.path.splitext(os.path.basename(image_file_object.name))[0]  # Get the base file name without extension
                                # extension = os.path.splitext(image_file_object.name)[1]  # Get the file extension
                                # Create a new image name based on its location
                                base_name,ext = image_info[i]
                                new_image_name = f"FileName {filename_without_extension} PageNumber Null ImageNumber {image_count}{ext}"
                                new_image_path = os.path.join(output_dir, new_image_name)

                                # Rename the image
                                if os.path.exists(original_image_path):
                                    shutil.move(original_image_path, new_image_path)

                                    # Update the placeholder in the paragraph
                                    new_placeholder = f"----media/ImageNumber:{image_count} PageNumber:Null of FileName:{filename_without_extension}----"
                                    paragraph = paragraph.replace(f"----media/{image_filename}----", new_placeholder)
                                    cell[paragraph_index] = paragraph
                                    image_count += 1
                                    i += 1
                            # print(paragraph)
                            texts += paragraph + "\n"
            return texts

        texts = extract_and_rename_images(file_content, output_path_byfile)
        logger.debug(f"texts is:::{texts}",)

    elif extension=="pptx":
        # temp_path = os.path.join(filename)
        # file.seek(0)
        # file.save(temp_path)
        # loader = UnstructuredPowerPointLoader(temp_path)
        # data = loader.load()
        # raw_text = raw_text.join(document.page_content for document in data)
        # os.remove(temp_path)
        def iter_picture_shapes(prs):
            slide_number = 1
            # image_number = 1
            # img_names = []
            for slide in prs.slides:
                image_number = 1
                logger.debug(f"slide {slide}",)
                for shape in slide.shapes:
                    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                        for s in shape.shapes:
                            if s.shape_type == MSO_SHAPE_TYPE.PICTURE:
                                image = shape.image
                                logger.debug(f"image_number {image_number}",)
                                image_filename = f'FileName {filename_without_extension} SlideNumber {slide_number} ImageNumber {image_number}.{image.ext}'
                                # img = f'SlideNumber:{slide_number} of FileName:{filename_without_extension}-ImageNumber {image_number}'
                                image_number += 1
                                logger.debug(image_filename)
                                # img_names.append(img)

                                image_path = os.path.join(output_path_byfile, image_filename)
                                with open(image_path, "wb") as fp:
                                    fp.write(image.blob)

                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        image = shape.image
                        logger.debug(f"image_number {image_number}",)
                        image_filename = f'FileName {filename_without_extension} SlideNumber {slide_number} ImageNumber {image_number}.{image.ext}'
                        # img = f'SlideNumber:{slide_number} of FileName:{filename_without_extension} with ImageNumber:{image_number}\n'
                        image_number += 1
                        logger.debug(image_filename)
                        # img_names.append(img)
                        image_path = os.path.join(output_path_byfile, image_filename)
                        with open(image_path, "wb") as fp:
                            fp.write(image.blob)
                slide_number += 1  


        iter_picture_shapes(Presentation(file_content))

        # langchain unstructuredworddoc method
        temp_path = os.path.join(f"{filename}{session_var}")
        file.seek(0)
        file.save(temp_path)
        loader = UnstructuredPowerPointLoader(temp_path,mode='elements')
        data = loader.load()
        logger.debug(f"data:\n{data}",)

        # Step 1: Collect content for each page number
        page_contents = {}
        for doc in data:
            # Access the metadata and page content correctly
            page_number = doc.metadata.get('page_number')
            if page_number is not None:
                if page_number not in page_contents:
                    page_contents[page_number] = []
                page_contents[page_number].append(doc.page_content)

        # Step 2: Combine the content for each page number
        # combined_page_contents = [{'page_number': page,'filename': filename, 'page_content': ' '.join(contents)} for page, contents in page_contents.items()]

        combined_page_contents = [
            {
                'SlideNumber': page,
                'FileName': filename_without_extension,
                'page_content': f"{' '.join(contents)} End of SlideNumber:{page} with Filename:{filename_without_extension} ----"
            }
            for page, contents in page_contents.items()
        ]

        texts = str(combined_page_contents)
        logger.debug(texts)
        os.remove(temp_path)

    elif extension=="txt":
        logger.debug(f"TExt file name is ::{filename}")
        temp_path = os.path.join(f"{filename}{session_var}")
        file.seek(0)
        file.save(temp_path)
        loader = TextLoader(temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content for document in data)
        os.remove(temp_path)

    # chunking recursively without semantic search, this does not uses openai embeddings for chunking
    text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = 1536,
    chunk_overlap  = 0,
    length_function = len
    )
    # uses openai embeddings for chunking, costs time and money but gives good performances, not ideal for real-time
    # text_splitter = SemanticChunker(OpenAIEmbeddings(), breakpoint_threshold_type="percentile", number_of_chunks= 10000)
    logger.debug("Before Embeddings!",)
    
    logger.debug("Now Doing Embeddings!")
    
    docsearch = None

    try:
        if texts:
            logger.debug("Running Text Merged (Pdfs other than extractedcontent.pdf)")
            text_splitter_formerged = RecursiveCharacterTextSplitter(chunk_size=1536, chunk_overlap=128, length_function=len)
            text_chunks = text_splitter_formerged.split_text(texts)

            batch_size = 100  # As per the limit mentioned in your error
            total_chunks = len(text_chunks)
            logger.debug(f"total_chunks: {total_chunks}",)

            for i in range(0, total_chunks, batch_size):
                batch = text_chunks[i:i + batch_size]

                docsearch = FAISS.from_texts(batch, embeddings)
                logger.debug(f"docsearch made for batch,{len(batch)} of the total {total_chunks}")

        elif raw_text:
            raw_text_splitted_chunks = text_splitter.split_text(raw_text)

            batch_size = 100  # As per the limit mentioned in your error
            total_chunks = len(raw_text_splitted_chunks)
            logger.debug(f"total_chunks: {total_chunks}",)

            for i in range(0, total_chunks, batch_size):
                batch_raw_text = raw_text_splitted_chunks[i:i + batch_size]

                docsearch = FAISS.from_texts(batch_raw_text, embeddings)
                logger.debug(f"docsearch made for batch,{len(batch_raw_text)} of the total {total_chunks}")

    except Exception as e:
        logger.error(f"Error with vectorization:{str(e)}")

    logger.debug("docsearch made")
    return docsearch


def PRODUCE_LEARNING_OBJ_COURSE(query, docsearch, llm, model_type):
    logger.debug("PRODUCE_LEARNING_OBJ_COURSE Initiated!")
    docs = docsearch.similarity_search(query, k=3)
    docs_main = " ".join([d.page_content for d in docs])
    if model_type=="gemini":
        chain = LLMChain(prompt=PROMPTS.prompt_LO_CA_GEMINI, llm=llm.bind(generation_config={"response_mime_type": "application/json"}))    
    else:
        chain = LLMChain(prompt=PROMPTS.prompt_LO_CA_GEMINI, llm=llm.bind(response_format={"type": "json_object"}))
    return chain, docs_main, query

def RE_SIMILARITY_SEARCH(query, docsearch, output_path, model_type, summarize_images, language):
    logger.debug("RE_SIMILARITY_SEARCH Initiated!")
    docs = docsearch.similarity_search(query, k=3)
    logger.debug(f"docs from RE_SIMILARITY_SEARCH:\n{docs}",)
    if summarize_images == "on":
        logger.debug(f"Tells me to summarize images, {summarize_images}")
        PageNumberList = []
        for relevant_doc in docs:
            relevant_doc = relevant_doc.page_content
            logger.debug(relevant_doc)

            pattern_this_pptx = r"'SlideNumber': (\d+), 'FileName': '(.+?)'"        # f'SlideNumber:{slide_number} of FileName:{filename_without_extension}-ImageNumber {image_number}'
            # Find all matches for "[This Page is PageNumber:]"
            matches_this_pptx = re.findall(pattern_this_pptx, relevant_doc)

            pattern_this_end_pptx = r"End of SlideNumber:(\d+) with Filename:(.+?) ----"        # f'SlideNumber:{slide_number} of FileName:{filename_without_extension}-ImageNumber {image_number}'
            # Find all matches for "[This Page is PageNumber:]"
            matches_this_end_pptx = re.findall(pattern_this_end_pptx, relevant_doc)


            pattern_this_doc = r'----media/ImageNumber:(\d+) PageNumber:Null of FileName:(.+)----'
            matches_this_doc = re.findall(pattern_this_doc, relevant_doc)
            
            pattern_end = r'End of PageNumber:(\d+) of file name:(.+)\n'
            pattern_this_page = r'The Content of PageNumber:(\d+) of file name:(.+) is:\n'
            # Find all matches for "End of PageNumber:"
            matches_end = re.findall(pattern_end, relevant_doc)

            # Find all matches for "[This Page is PageNumber:]"
            matches_this_page = re.findall(pattern_this_page, relevant_doc)

            # Combine the matches
            for num in matches_this_page + matches_end + matches_this_doc + matches_this_pptx + matches_this_end_pptx:
                PageNumberList.append(num)

            PageNumberList = list(set(PageNumberList))
            logger.debug(f"PageNumberList:\n{PageNumberList}",)

        image_elements = []
        image_summaries = []

        def encode_image(image_path):
            basename = os.path.basename(image_path)
            with Image.open(image_path) as img:
                width, height = img.size
                logger.debug(f"{basename} size is {width},{height}")
                if width*height > 262144:
                    # Resize the image
                    img = img.resize((512, 512))
                    # Save the resized image to a temporary file
                    basenama = os.path.basename(image_path)
                    extensiona = basenama.rsplit('.', 1)[1].lower()

                    temp_patha = image_path + f"_temp_img.{extensiona}"
                    img.save(temp_patha)
                
                    # Encode the resized image
                    with open(temp_patha, "rb") as f:
                        encoded_image = base64.b64encode(f.read()).decode('utf-8')

                    # Remove the temporary file
                    os.remove(temp_patha)
                else:
                    logger.debug(f"{basename} is less than 262144 having {width}, {height}")
                    with open(image_path, "rb") as f:
                        encoded_image = base64.b64encode(f.read()).decode('utf-8')

                return encoded_image



        def summarize_image(encoded_image, basename, language):
            prompt = [
                SystemMessage(content="You are a bot that is good at analyzing images."),
                HumanMessage(content=[
                    {
                        "type": "text",
                        "text": f"Describe the contents of this image in the language of {language}, since your responses are given to {language} speakers and they can only understand the language of {language}. Tell what FileName, PageNumber/SlideNumber and ImageNumber of this image is by seeing this information: {basename}. Your output should look like this: 'This image that belongs to FileName: ..., PageNumber: ..., ImageNumber: .... In this Image ...' or in case of SlideNumber available 'This image that belongs to FileName: ..., SlideNumber: ..., ImageNumber: .... In this Image ...' !!!WARNING: Exact, absolutely Unchanged File name of the image must be mentioned as found in {basename}. File name may contain special characters such as hyphens (-), underscores (_), semicolons (;), spaces, and others, so this should be kept in mind!!!"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encoded_image}"
                        },
                    },
                ])
            ]

            prompt_gemini = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": f"Describe the contents of this image in the language of {language}, since your responses are given to {language} speakers and they can only understand the language of {language}. Tell what FileName, PageNumber/SlideNumber and ImageNumber of this image is by seeing this information: {basename}. Your output should look like this: 'This image that belongs to FileName: ..., PageNumber: ..., ImageNumber: .... In this Image ...' or in case of SlideNumber available 'This image that belongs to FileName: ..., SlideNumber: ..., ImageNumber: .... In this Image ...' !!!WARNING: Exact, absolutely Unchanged File name of the image must be mentioned as found in {basename}. File name may contain special characters such as hyphens (-), underscores (_), semicolons (;), spaces, and others, so this should be kept in mind!!!",
                    },  # You can optionally provide text parts
                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{encoded_image}"},
                ]
            )

            if model_type == 'gemini':
                logger.debug("Gemini summarizing images NOW")
                response = ChatGoogleGenerativeAI(model="gemini-1.5-flash",temperature=0,max_output_tokens=200).invoke([prompt_gemini])
                return response.content
            else:
                logger.debug("Openai summarizing images NOW")
                response = AzureChatOpenAI(deployment_name="gpt-4o", temperature=0, max_tokens=200,
                                            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")).invoke(prompt)
                return response.content

        for root, dirs, files in os.walk(output_path):
            for i in files:
                if i.endswith(('.png', '.jpg', '.jpeg')):
                    for page_number, file in PageNumberList:
                        if f"FileName {file} PageNumber {page_number}" in i:
                            image_path = os.path.join(root, i)
                            basename = os.path.basename(image_path)
                            logger.debug(os.path.basename(image_path))
                            encoded_image = encode_image(image_path)
                            image_elements.append(encoded_image)
                            summary = summarize_image(encoded_image,basename, language)
                            image_summaries.append(summary)
                        elif f"FileName {file} PageNumber Null ImageNumber {page_number}" in i:
                            image_path = os.path.join(root, i)
                            basename = os.path.basename(image_path)
                            logger.debug(os.path.basename(image_path))
                            encoded_image = encode_image(image_path)
                            image_elements.append(encoded_image)
                            summary = summarize_image(encoded_image,basename, language)
                            image_summaries.append(summary)
                        elif f"FileName {file} SlideNumber {page_number}" in i:
                            image_path = os.path.join(root, i)
                            basename = os.path.basename(image_path)
                            logger.debug(os.path.basename(image_path))
                            encoded_image = encode_image(image_path)
                            image_elements.append(encoded_image)
                            summary = summarize_image(encoded_image,basename, language)
                            image_summaries.append(summary)

        logger.debug(f"image_summaries::\n{image_summaries}",)

        image_summaries_string = "\n".join(image_summaries) #convert list to string to add in the langchain Document data type
        docs.append(Document(page_content=f"Useful Image/s for all the above content::\n{image_summaries_string}"))

    return docs


def TALK_WITH_RAG(scenario, content_areas, learning_obj, query, docs_main, llm, model_type, model_name,embeddings, language):
    logger.debug("TALK_WITH_RAG Initiated!")
    # if we are getting docs_main already from the process_data flask route then comment, else
    # UNcomment if you want more similarity_searching based on Learning obj and content areas!
    # docs = docsearch.similarity_search(query, k=3)
    # docs_main = " ".join([d.page_content for d in docs])
    responses = ''
    def is_json_parseable(json_string):
        try:
            json_object = json.loads(json_string)
        except ValueError as e:
            return False, str(e)
        return True, json_object

    if scenario == "auto":
        logger.debug(f"SCENARIO ====PROMPT{scenario}",)
        # chain = prompt | llm | {f"{llm_memory}": RunnablePassthrough()}
        

        ### SEMANTIC ROUTES LOGIC ###
        if model_type == 'gemini':
            llm_auto = ChatGoogleGenerativeAI(model=model_name,temperature=0.4, max_output_tokens=32) 
            llm_auto_chain = LLMChain(prompt=PROMPTS.promptSelector, llm=llm_auto.bind(generation_config={"response_mime_type": "application/json"})) 
        else:
            llm_auto =  AzureChatOpenAI(deployment_name=model_name, temperature=0.4, max_tokens=32,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
            llm_auto_chain = LLMChain(prompt=PROMPTS.promptSelector, llm=llm_auto.bind(response_format={"type": "json_object"}))
        
        selected = llm_auto_chain.run({"input_documents": docs_main, "human_input": query})

        logger.debug(f"Semantic Scenario Selected of NAME: {selected}",)

        gamified_route = ['gamified', 'gamified scenario','bot: gamified scenario']
        simulation_route = ['simulation', 'simulation scenario', 'bot: simulation scenario']
        linear_route = ['linear', 'linear scenario', 'bot: linear scenario']
        branched_route = ['branched', 'branched scenario', 'bot: branched scenario']

        gamified_route_embeddings = embeddings.embed_documents(gamified_route)
        simulation_route_embeddings = embeddings.embed_documents(simulation_route)
        linear_route_embeddings = embeddings.embed_documents(linear_route)
        branched_route_embeddings =  embeddings.embed_documents(branched_route)

        query_embedding = embeddings.embed_query(selected)

        gamified_similarity = cosine_similarity([query_embedding],gamified_route_embeddings)[0]
        simulation_similarity = cosine_similarity([query_embedding],simulation_route_embeddings)[0]
        linear_similarity = cosine_similarity([query_embedding], linear_route_embeddings)[0]
        branched_similarity = cosine_similarity([query_embedding], branched_route_embeddings)[0]

        max_similarity = max(max(gamified_similarity), max(simulation_similarity), max(linear_similarity), max(branched_similarity))

        ############################

        if max_similarity == max(gamified_similarity):
            logger.debug("Gamified Auto Selected")
            scenario = "gamified"

        elif max_similarity == max(linear_similarity):
            logger.debug("Linear Auto Selected")
            scenario = "linear"

        elif max_similarity == max(simulation_similarity):
            logger.debug(f"Simulation Auto Selected")
            scenario = "simulation"

        elif max_similarity == max(branched_similarity):
            logger.debug(f"Branched Auto Selected")
            scenario = "branched"

        else:
            logger.debug(f"AUTO SELECTION FAILED, Selecting Default Scenario of LINEAR SCENARIO")
            scenario = "linear"

    if scenario == "linear":
        logger.debug(f"SCENARIO ====prompt_linear : {scenario}")
        if model_type == 'gemini':
            chain = LLMChain(prompt=PROMPTS.prompt_linear,llm=llm)
        else:
            chain = LLMChain(prompt=PROMPTS.prompt_linear,llm=llm)   

        response = chain({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        
        is_valid, result = is_json_parseable(response['text'])
        countd=1
        while not is_valid and countd<=2:
            txt = response['text']
            logger.debug(f"CHAIN_RETRY BEGINS for the failed response:\n{txt}")
            ### REGEX to remove last incomplete id block ###
            modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
            if modified_txt:
                modified_txt = modified_txt[0]  # Get the matched string
            else:
                modified_txt = txt  # No match found, return original
            logger.debug(f"original:::\n{txt}")
            logger.debug(f"changed:::\n{modified_txt}")

            # Finding if corrupt edges exists further and to remove it via if loop
            find_edges = re.findall(r'.*}, "edges": \[', modified_txt, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}")
                # Using regex to replace the specific pattern
                modified_txt = re.sub(r'}(?=, "edges": \[)', '}]', modified_txt, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{modified_txt}")

            responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
            logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

            if model_type == 'gemini':
                chain_retry = LLMChain(prompt=PROMPTS.prompt_linear_retry,llm=llm)
            else:
                chain_retry = LLMChain(prompt=PROMPTS.prompt_linear_retry,llm=llm)

            response_retry = chain_retry({"incomplete_response": responses, "language":language})
            logger.debug(f"response contd... is:\n{response_retry['text']}",)

            responses = modified_txt + response_retry['text'] #changed modified_text to responses
            logger.debug(f"responses+continued Combined is:\n{responses}",)

            # Finding if corrupt edges exists AFTER combined prompts
            find_edges = re.findall(r'.*}, "edges": \[', responses, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                responses = re.sub(r'}(?=, "edges": \[)', '}]', responses, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{responses}", )

            response['text'] = responses

            is_valid, result = is_json_parseable(responses)
            logger.debug(f"Parseability status:\n{result}", )
            countd+=1
            logger.debug(f"contd count is:\n{countd}",)

        if is_valid == False and countd==3: #countd==4 shows while loop has exited with failure 
            logger.debug(f"The retry is also not parseable!\n{responses}", )
            max_attempts = 1  # Maximum number of attempts
            attempts = 1
            while attempts <= max_attempts:

                if model_type == 'gemini':
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_linear_simplify,llm=llm)
                else:
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_linear_simplify,llm=llm)

                response_retry_simplify = chain_simplify({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                is_valid_retry_simplify, result = is_json_parseable(response_retry_simplify['text'])
                if is_valid_retry_simplify == True:
                    response['text'] = response_retry_simplify['text']
                    logger.debug(f"Result successfull for simplified response:\n{response['text']}",)
                    break
                else:
                    logger.debug(f"Attempt {attempts} also failed to parse JSON. Error:\n {response_retry_simplify['text']}")
                    attempts += 1
                    

    elif scenario == "branched":
        logger.debug(f"SCENARIO ====branched : {scenario}",)
        
        if model_type == 'gemini':
            llm_setup = ChatGoogleGenerativeAI(model=model_name,temperature=0)
            llm_setup_continue = ChatGoogleGenerativeAI(model=model_name,temperature=0.1)
            chain = LLMChain(prompt=PROMPTS.prompt_branched,llm=llm)
        else:
            llm_setup = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )  
            llm_setup_continue = AzureChatOpenAI(deployment_name=model_name, temperature=0.1,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
            chain = LLMChain(prompt=PROMPTS.prompt_branched,llm=llm)   

        if model_type == 'gemini':
            chain1 = LLMChain(prompt=PROMPTS.prompt_branched_setup,llm=llm_setup)
        else:
            chain1 = LLMChain(prompt=PROMPTS.prompt_branched_setup,llm=llm_setup)

        response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        if "[END_OF_RESPONSE]" not in response1['text']:
            count_setup_retry = 0
            while "[END_OF_RESPONSE]" not in response1['text'] and count_setup_retry<=3:
                logger.debug("[END_OF_RESPONSE] not found")
                contd_response1 = response1['text'] + "[CONTINUE_EXACTLY_FROM_HERE]"
                chain_setup_retry = LLMChain(prompt=PROMPTS.prompt_branched_setup_continue,llm=llm_setup_continue)
                response1 = chain_setup_retry({"past_response": contd_response1,"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                logger.debug(f"CONTINUED Response 1 IS::\n{response1['text']}")
                response1['text'] = contd_response1 + response1['text']
                response1['text'] = re.sub(r'\[CONTINUE_EXACTLY_FROM_HERE\]', ' ', response1['text'])
                
                logger.debug(f"JOINED Response 1 IS::\n{response1['text']}")
                count_setup_retry += 1
        else:
            logger.debug(f"Response 1 is::\n{response1['text']}",)


        response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        
        is_valid, result = is_json_parseable(response['text'])
        countd=1
        while not is_valid and countd<=2:
            txt = response['text']
            logger.debug(f"CHAIN_RETRY BEGINS for the failed response:\n{txt}", )
            ### REGEX to remove last incomplete id block ###
            modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
            if modified_txt:
                modified_txt = modified_txt[0]  # Get the matched string
            else:
                modified_txt = txt  # No match found, return original
            logger.debug(f"original:::\n{txt}",)
            logger.debug(f"changed:::\n{modified_txt}",)

            # Finding if corrupt edges exists further and to remove it via if loop
            find_edges = re.findall(r'.*}, "edges": \[', modified_txt, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                modified_txt = re.sub(r'}(?=, "edges": \[)', '}]', modified_txt, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{modified_txt}", )

            responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
            logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

            if model_type == 'gemini':
                chain_retry = LLMChain(prompt=PROMPTS.prompt_branched_retry,llm=llm)
            else:
                chain_retry = LLMChain(prompt=PROMPTS.prompt_branched_retry,llm=llm)

            response_retry = chain_retry({"incomplete_response": responses,"micro_subtopics":response1['text'], "language":language})
            logger.debug(f"response contd... is:\n{response_retry['text']}",)

            responses = modified_txt + response_retry['text'] #changed modified_text to responses
            logger.debug(f"responses+continued Combined is:\n{responses}",)

            # Finding if corrupt edges exists AFTER combined prompts
            find_edges = re.findall(r'.*}, "edges": \[', responses, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                responses = re.sub(r'}(?=, "edges": \[)', '}]', responses, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{responses}", )

            response['text'] = responses

            is_valid, result = is_json_parseable(responses)
            logger.debug(f"Parseability status:\n{result}", )
            countd+=1
            logger.debug(f"contd count is:\n{countd}",)

        if is_valid == False and countd==3: #countd==4 shows while loop has exited with failure 
            logger.debug(f"The retry is also not parseable!:\n{responses}", )
            max_attempts = 1  # Maximum number of attempts
            attempts = 1
            while attempts <= max_attempts:

                if model_type == 'gemini':
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_branched_simplify,llm=llm)
                else:
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_branched_simplify,llm=llm)

                response_retry_simplify = chain_simplify({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                is_valid_retry_simplify, result = is_json_parseable(response_retry_simplify['text'])
                if is_valid_retry_simplify == True:
                    response['text'] = response_retry_simplify['text']
                    logger.debug(f"Result successfull for simplified response:\n{response['text']}",)
                    break
                else:
                    logger.debug(f"Attempt {attempts} also failed to parse JSON. Error:\n {response_retry_simplify['text']}")
                    attempts += 1
                    

    elif scenario == "simulation":
        logger.debug(f"SCENARIO ====prompt_simulation_pedagogy : {scenario}",)
        # summarized first, then response
        if model_type == 'gemini':
            llm_setup = ChatGoogleGenerativeAI(model=model_name,temperature=0.3)
            llm_setup_continue = ChatGoogleGenerativeAI(model=model_name,temperature=0.1)
            chain = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_gemini,llm=llm)
        else:
            llm_setup = AzureChatOpenAI(deployment_name=model_name, temperature=0.3,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )  
            llm_setup_continue = AzureChatOpenAI(deployment_name=model_name, temperature=0.1,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        ) 
            chain = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_gemini,llm=llm)   

        if model_type == 'gemini':
            chain1 = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_setup,llm=llm_setup)
        else:
            chain1 = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_setup,llm=llm_setup)

        response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        if "[END_OF_RESPONSE]" not in response1['text']:
            count_setup_retry = 0
            while "[END_OF_RESPONSE]" not in response1['text'] and count_setup_retry<=3:
                logger.debug("[END_OF_RESPONSE] not found")
                contd_response1 = response1['text'] + "[CONTINUE_EXACTLY_FROM_HERE]"
                chain_setup_retry = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_setup_continue,llm=llm_setup_continue)
                response1 = chain_setup_retry({"past_response": contd_response1,"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                logger.debug(f"CONTINUED Response 1 IS::\n{response1['text']}")
                response1['text'] = contd_response1 + response1['text']
                response1['text'] = re.sub(r'\[CONTINUE_EXACTLY_FROM_HERE\]', ' ', response1['text'])
                
                logger.debug(f"JOINED Response 1 IS::\n{response1['text']}")
                count_setup_retry += 1
        else:
            logger.debug(f"Response 1 is::\n{response1['text']}",)


        response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        
        is_valid, result = is_json_parseable(response['text'])
        countd=1
        while not is_valid and countd<=2:
            txt = response['text']
            logger.debug(f"CHAIN_RETRY BEGINS for the failed response:\n{txt}", )
            ### REGEX to remove last incomplete id block ###
            modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
            if modified_txt:
                modified_txt = modified_txt[0]  # Get the matched string
            else:
                modified_txt = txt  # No match found, return original
            logger.debug(f"original:::\n{txt}",)
            logger.debug(f"changed:::\n{modified_txt}",)

            # Finding if corrupt edges exists further and to remove it via if loop
            find_edges = re.findall(r'.*}, "edges": \[', modified_txt, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                modified_txt = re.sub(r'}(?=, "edges": \[)', '}]', modified_txt, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{modified_txt}", )

            responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
            logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

            if model_type == 'gemini':
                chain_retry = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_retry_gemini,llm=llm)
            else:
                chain_retry = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_retry_gemini,llm=llm)

            response_retry = chain_retry({"incomplete_response": responses,"simulation_story":response1['text'], "language":language})
            logger.debug(f"response contd... is:\n{response_retry['text']}",)

            responses = modified_txt + response_retry['text'] #changed modified_text to responses
            logger.debug(f"responses+continued Combined is:\n{responses}",)

            # Finding if corrupt edges exists AFTER combined prompts
            find_edges = re.findall(r'.*}, "edges": \[', responses, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                responses = re.sub(r'}(?=, "edges": \[)', '}]', responses, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{responses}", )

            response['text'] = responses

            is_valid, result = is_json_parseable(responses)
            logger.debug(f"Parseability status:\n{result}", )
            countd+=1
            logger.debug(f"contd count is:{countd}",)

        if is_valid == False and countd==3: #countd==4 shows while loop has exited with failure 
            logger.debug(f"The retry is also not parseable!:\n{responses}", )
            max_attempts = 1  # Maximum number of attempts
            attempts = 1
            while attempts <= max_attempts:

                if model_type == 'gemini':
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_gemini_simplify,llm=llm)
                else:
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_simulation_pedagogy_gemini_simplify,llm=llm)

                response_retry_simplify = chain_simplify({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                is_valid_retry_simplify, result = is_json_parseable(response_retry_simplify['text'])
                if is_valid_retry_simplify == True:
                    response['text'] = response_retry_simplify['text']
                    logger.debug(f"Result successfull for simplified response:\n{response['text']}",)
                    break
                else:
                    logger.debug(f"Attempt {attempts} also failed to parse JSON. Error:\n {response_retry_simplify['text']}")
                    attempts += 1
                            

    elif scenario == "gamified":
        logger.debug(f"SCENARIO ====prompt_gamified : {scenario}",)
        if model_type == 'gemini':
            llm_setup = ChatGoogleGenerativeAI(model=model_name,temperature=0)
            llm_setup_continue = ChatGoogleGenerativeAI(model=model_name,temperature=0.1)
            chain = LLMChain(prompt=PROMPTS.prompt_gamified_json,llm=llm)
        else:
            llm_setup = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )  
            llm_setup_continue = AzureChatOpenAI(deployment_name=model_name, temperature=0.1,
                                        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                        )
            chain = LLMChain(prompt=PROMPTS.prompt_gamified_json,llm=llm)   

        if model_type == 'gemini':
            chain1 = LLMChain(prompt=PROMPTS.prompt_gamified_setup,llm=llm_setup)
        else:
            chain1 = LLMChain(prompt=PROMPTS.prompt_gamified_setup,llm=llm_setup)

        response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        if "[END_OF_RESPONSE]" not in response1['text']:
            count_setup_retry = 0
            while "[END_OF_RESPONSE]" not in response1['text'] and count_setup_retry<=3:
                logger.debug("[END_OF_RESPONSE] not found")
                contd_response1 = response1['text'] + "[CONTINUE_EXACTLY_FROM_HERE]"
                chain_setup_retry = LLMChain(prompt=PROMPTS.prompt_gamified_setup_continue,llm=llm_setup_continue)
                response1 = chain_setup_retry({"past_response": contd_response1,"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                logger.debug(f"CONTINUED Response 1 IS::\n{response1['text']}")
                response1['text'] = contd_response1 + response1['text']
                response1['text'] = re.sub(r'\[CONTINUE_EXACTLY_FROM_HERE\]', ' ', response1['text'])
                
                logger.debug(f"JOINED Response 1 IS::\n{response1['text']}")
                count_setup_retry += 1
        else:
            logger.debug(f"Response 1 is::\n{response1['text']}",)


        response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
        
        is_valid, result = is_json_parseable(response['text'])
        countd=1
        while not is_valid and countd<=2:
            txt = response['text']
            logger.debug(f"CHAIN_RETRY BEGINS for the failed response:\n{txt}", )
            ### REGEX to remove last incomplete id block ###
            modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
            if modified_txt:
                modified_txt = modified_txt[0]  # Get the matched string
            else:
                modified_txt = txt  # No match found, return original
            logger.debug(f"original:::\n{txt}",)
            logger.debug(f"changed:::\n{modified_txt}",)

            # Finding if corrupt edges exists further and to remove it via if loop
            find_edges = re.findall(r'.*}, "edges": \[', modified_txt, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                modified_txt = re.sub(r'}(?=, "edges": \[)', '}]', modified_txt, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{modified_txt}", )

            responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
            logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

            if model_type == 'gemini':
                chain_retry = LLMChain(prompt=PROMPTS.prompt_gamified_pedagogy_retry_gemini,llm=llm)
            else:
                chain_retry = LLMChain(prompt=PROMPTS.prompt_gamified_pedagogy_retry_gemini,llm=llm)

            response_retry = chain_retry({"incomplete_response": responses,"exit_game_story":response1['text'], "language":language})
            logger.debug(f"response contd... is:\n{response_retry['text']}",)

            responses = modified_txt + response_retry['text'] #changed modified_text to responses
            logger.debug(f"responses+continued Combined is:\n{responses}",)

            # Finding if corrupt edges exists AFTER combined prompts
            find_edges = re.findall(r'.*}, "edges": \[', responses, re.DOTALL)
            if find_edges:
                find_edges = find_edges[0]  # Get the matched string
                logger.debug(f"Corrupt edges found:\n{find_edges}",)
                # Using regex to replace the specific pattern
                responses = re.sub(r'}(?=, "edges": \[)', '}]', responses, flags=re.DOTALL)
                logger.debug(f"Corrected corrupt edges:\n{responses}", )

            response['text'] = responses

            is_valid, result = is_json_parseable(responses)
            logger.debug(f"Parseability status:\n{result}", )
            countd+=1
            logger.debug(f"contd count is:{countd}",)

        if is_valid == False and countd==3: #countd==4 shows while loop has exited with failure 
            logger.debug(f"The retry is also not parseable!:\n{responses}", )
            max_attempts = 1  # Maximum number of attempts
            attempts = 1
            while attempts <= max_attempts:

                if model_type == 'gemini':
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_gamify_pedagogy_gemini_simplify,llm=llm)
                else:
                    chain_simplify = LLMChain(prompt=PROMPTS.prompt_gamify_pedagogy_gemini_simplify,llm=llm)

                response_retry_simplify = chain_simplify({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj, "language":language})
                is_valid_retry_simplify, result = is_json_parseable(response_retry_simplify['text'])
                if is_valid_retry_simplify == True:
                    response['text'] = response_retry_simplify['text']
                    logger.debug(f"Result successfull for simplified response:\n{response['text']}",)
                    break
                else:
                    logger.debug(f"Attempt {attempts} also failed to parse JSON. Error:\n {response_retry_simplify['text']}")
                    attempts += 1
                    
     
    logger.debug(f"The output is as follows::\n{response['text']}",)
    return response['text'], scenario

def REPAIR_SHADOW_EDGES(scenario, original_txt,model_type, model_name, language):
    

    if model_type == 'gemini':
        llm = ChatGoogleGenerativeAI(model=model_name,temperature=0)
    else:
        llm = AzureChatOpenAI(deployment_name=model_name, temperature=0,
                                    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION")
                                )  
        
    def is_json_parseable(json_string):
        try:
            json_object = json.loads(json_string)
        except ValueError as e:
            return False, str(e)
        return True, json_object

    def validate_edges(json_data):
        # txt_string = json.dumps(json_data)  # Convert dictionary to JSON string
        # json_data = json.loads(txt_string)  # Convert JSON string into dictionary
        json_data = json.loads(json_data)  # Convert JSON string into dictionary
        node_ids = {node['id'] for node in json_data['nodes']}
        error_flag = False

        for edge in json_data['edges']:
            source_exists = edge['source'] in node_ids
            target_exists = edge['target'] in node_ids

            if not source_exists or not target_exists:
                logger.debug(f"Error occured:\n{edge}")
                edge['SHADOW EDGE BLOCK'] = 'SHADOW EDGES IN THIS BLOCK'  # Add error directly to the edge
                error_flag = True
                # If you want to find all errors, remove the break statement
                # break

        shadow_result = json.dumps(json_data, indent=4)
        return shadow_result, error_flag

    output, error_flag = validate_edges(original_txt)
    logger.debug(f"error_flag: {error_flag}")

    if error_flag == True:

        logger.debug(f"Error flag is: {error_flag} and so output is:\n{output}")

        if scenario == "linear":

            chain = LLMChain(prompt=PROMPTS.prompt_linear_shadow_edges, llm=llm.bind(generation_config={"response_mime_type": "application/json"}))
            shadow_response = chain({"output": output,"language":language})
            is_valid, result = is_json_parseable(shadow_response['text'])
            countd=0
            while not is_valid and countd<=3:
                txt = shadow_response['text']
                modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
                if modified_txt:
                    modified_txt = modified_txt[0]  # Get the matched string
                else:
                    modified_txt = txt  # No match found, return original
                logger.debug(f"original:::\n{txt}")
                logger.debug(f"changed:::\n{modified_txt}")

                responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
                logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

                chain_edges_retry = LLMChain(prompt=PROMPTS.prompt_linear_shadow_edges_retry, llm=llm)
                response_retry = chain_edges_retry({"incomplete_response": responses, "output":output, "language":language})
                logger.debug(f"response contd... is:\n{response_retry['text']}",)

                responses = modified_txt + response_retry['text'] #changed modified_text to responses
                logger.debug(f"responses+continued Combined is:\n{responses}",)
                
                shadow_response['text'] = responses

                is_valid, result = is_json_parseable(shadow_response['text'])
                logger.debug(f"Parseability status:\n{result}", )
                countd+=1
                logger.debug(f"contd count is:\n{countd}",)

            logger.debug("Success shadow repair!:",shadow_response['text'])
            shadow_response = shadow_response['text']
            logger.debug(f"shadow_response type before: {type(shadow_response)}")
            logger.debug(f"output type before: {type(output)}")

            shadow_response = json.loads(shadow_response)  # Convert JSON string into dictionary
            output = json.loads(output)  # Convert JSON string into dictionary

            logger.debug(f"shadow_response type after: {type(shadow_response)} and output type after {type(output)}")

            output['edges']  = shadow_response['edges']  
            logger.debug(output)
            is_valid_output, result = is_json_parseable(output)

            if is_valid_output == False:
                output = original_txt
                logger.debug(f"The output was not parseable hence reverting to original_txt to this response:\n{output}")


        elif scenario == "branched":

            chain = LLMChain(prompt=PROMPTS.prompt_branched_shadow_edges, llm=llm.bind(generation_config={"response_mime_type": "application/json"}))
            shadow_response = chain({"output": output,"language":language})
            is_valid, result = is_json_parseable(shadow_response['text'])
            countd=0
            while not is_valid and countd<=3:
                txt = shadow_response['text']
                modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
                if modified_txt:
                    modified_txt = modified_txt[0]  # Get the matched string
                else:
                    modified_txt = txt  # No match found, return original
                logger.debug(f"original:::\n{txt}")
                logger.debug(f"changed:::\n{modified_txt}")

                responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
                logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

                chain_edges_retry = LLMChain(prompt=PROMPTS.prompt_branched_shadow_edges_retry, llm=llm)
                response_retry = chain_edges_retry({"incomplete_response": responses, "output":output, "language":language})
                logger.debug(f"response contd... is:\n{response_retry['text']}",)

                responses = modified_txt + response_retry['text'] #changed modified_text to responses
                logger.debug(f"responses+continued Combined is:\n{responses}",)
                
                shadow_response['text'] = responses

                is_valid, result = is_json_parseable(shadow_response['text'])
                logger.debug(f"Parseability status:\n{result}", )
                countd+=1
                logger.debug(f"contd count is:\n{countd}",)

            logger.debug("Success shadow repair!:",shadow_response['text'])
            shadow_response = shadow_response['text']
            logger.debug(f"shadow_response type before: {type(shadow_response)}")
            logger.debug(f"output type before: {type(output)}")

            shadow_response = json.loads(shadow_response)  # Convert JSON string into dictionary
            output = json.loads(output)  # Convert JSON string into dictionary

            logger.debug(f"shadow_response type after: {type(shadow_response)} and output type after {type(output)}")

            output['edges']  = shadow_response['edges']  
            logger.debug(output)
            is_valid_output, result = is_json_parseable(output)

            if is_valid_output == False:
                output = original_txt
                logger.debug(f"The output was not parseable hence reverting to original_txt to this response:\n{output}")


        elif scenario == "simulation":

            chain = LLMChain(prompt=PROMPTS.prompt_simulation_shadow_edges, llm=llm.bind(generation_config={"response_mime_type": "application/json"}))
            shadow_response = chain({"output": output,"language":language})
            is_valid, result = is_json_parseable(shadow_response['text'])
            countd=0
            while not is_valid and countd<=3:
                txt = shadow_response['text']
                modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
                if modified_txt:
                    modified_txt = modified_txt[0]  # Get the matched string
                else:
                    modified_txt = txt  # No match found, return original
                logger.debug(f"original:::\n{txt}")
                logger.debug(f"changed:::\n{modified_txt}")

                responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
                logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

                chain_edges_retry = LLMChain(prompt=PROMPTS.prompt_simulation_shadow_edges_retry, llm=llm)
                response_retry = chain_edges_retry({"incomplete_response": responses, "output":output, "language":language})
                logger.debug(f"response contd... is:\n{response_retry['text']}",)

                responses = modified_txt + response_retry['text'] #changed modified_text to responses
                logger.debug(f"responses+continued Combined is:\n{responses}",)
                
                shadow_response['text'] = responses

                is_valid, result = is_json_parseable(shadow_response['text'])
                logger.debug(f"Parseability status:\n{result}", )
                countd+=1
                logger.debug(f"contd count is:\n{countd}",)

            logger.debug("Success shadow repair!:",shadow_response['text'])
            shadow_response = shadow_response['text']
            logger.debug(f"shadow_response type before: {type(shadow_response)}")
            logger.debug(f"output type before: {type(output)}")

            shadow_response = json.loads(shadow_response)  # Convert JSON string into dictionary
            output = json.loads(output)  # Convert JSON string into dictionary

            logger.debug(f"shadow_response type after: {type(shadow_response)} and output type after {type(output)}")

            output['edges']  = shadow_response['edges']  
            logger.debug(output)
            is_valid_output, result = is_json_parseable(output)

            if is_valid_output == False:
                output = original_txt
                logger.debug(f"The output was not parseable hence reverting to original_txt to this response:\n{output}")


        elif scenario == "gamified":

            chain = LLMChain(prompt=PROMPTS.prompt_gamify_shadow_edges, llm=llm.bind(generation_config={"response_mime_type": "application/json"}))
            shadow_response = chain({"output": output,"language":language})
            is_valid, result = is_json_parseable(shadow_response['text'])
            countd=0
            while not is_valid and countd<=3:
                txt = shadow_response['text']
                modified_txt = re.findall(r'.*},', txt, re.DOTALL) # Finds last },
                if modified_txt:
                    modified_txt = modified_txt[0]  # Get the matched string
                else:
                    modified_txt = txt  # No match found, return original
                logger.debug(f"original:::\n{txt}")
                logger.debug(f"changed:::\n{modified_txt}")

                responses = modified_txt + "\n[CONTINUE_EXACTLY_FROM_HERE]" #changed txt
                logger.debug(f"\nThe responses_modification to LLM is:\n{responses}",)

                chain_edges_retry = LLMChain(prompt=PROMPTS.prompt_gamify_shadow_edges_retry, llm=llm)
                response_retry = chain_edges_retry({"incomplete_response": responses, "output":output, "language":language})
                logger.debug(f"response contd... is:\n{response_retry['text']}",)

                responses = modified_txt + response_retry['text'] #changed modified_text to responses
                logger.debug(f"responses+continued Combined is:\n{responses}",)
                
                shadow_response['text'] = responses

                is_valid, result = is_json_parseable(shadow_response['text'])
                logger.debug(f"Parseability status:\n{result}", )
                countd+=1
                logger.debug(f"contd count is:\n{countd}",)

            logger.debug("Success shadow repair!:",shadow_response['text'])
            shadow_response = shadow_response['text']
            logger.debug(f"shadow_response type before: {type(shadow_response)}")
            logger.debug(f"output type before: {type(output)}")

            shadow_response = json.loads(shadow_response)  # Convert JSON string into dictionary
            output = json.loads(output)  # Convert JSON string into dictionary

            logger.debug(f"shadow_response type after: {type(shadow_response)} and output type after {type(output)}")

            output['edges']  = shadow_response['edges']  
            logger.debug(output)
            is_valid_output, result = is_json_parseable(output)

            if is_valid_output == False:
                output = original_txt
                logger.debug(f"The output was not parseable hence reverting to original_txt to this response:\n{output}")


    else:
        logger.debug(f"Since error_flag is {error_flag}, no shadow edges found!")

    return output



def ANSWER_IMG(response_text, llm,relevant_doc,language,model_type):
    # prompt_template_img =PromptTemplate( 
    # input_variables=["response_text","context"],
    # template="""
    # Provided the context, look at the Images that are mentioned in the 'response_text': {response_text}. Provide a brief summary of those 
    # images stored in the 'context': {context}.
    # Format of Reply (The number of Images and their description may vary, depends on what is instructed in the
    # 'response_text'. If only one image is mentioned in the 'response_text', then you should include Image1 only. If there are 2 or more images then your reply should
    # also have same images as mentioned in the 'response_text'!):
    # {{"Image1": "file_name_..._page_..._image_...",
    # "Description1": "...",
    # "Image2": "file_name_..._page_..._image_...",
    # "Description2": "..."
    # and so on
    # }}
    # Warning: Include the complete schema of name defined. The complete schema of name includes
    # "file_name_..._page_..._image_..."
    # Take great care for the underscores. They are to be used exactly as defined. Also take 
    # extreme caution at the file_name since the file might be having its own - and _ which is not to be
    # tampered with in any way and should remain exactly the same!
    # [WARNING: The ... presents page number as int and image number as int. But, for the file_name_ it represents
    # as the file name itself which may have its own dashes or underscores or brackets. Whatever the file name
    # you found in the 'context', make sure you use the same name. ]
    # Answer():
    # """
    # )



    # chain = LLMChain(prompt=prompt_template_img,llm=llm)
    # img_response = chain.run({"response_text": response_text, "context": relevant_doc})
    # print("img_response is::",img_response)
###

    class image_loc(BaseModel):
        FileName: str = Field(description="Exact, absolutely Unchanged File name of the image as mentioned in the 'Context'. File name may contain special characters such as hyphens (-), underscores (_), semicolons (;), spaces, and others.")
        PageNumber: Optional[str] = Field(description="If available, write page number of the image. 'Null' if not available. !!!DO NOT USE PageNumber if SlideNumber is available.!!!")
        SlideNumber: Optional[str] = Field(description="If available, slide number of the image.")
        ImageNumber: int = Field(description="image number of the image")
        Description: str = Field(description="Description detail of the image")

    class image(BaseModel):
        Image: List[image_loc] = Field(description="image_loc")

    parser = JsonOutputParser(pydantic_object=image)

    prompt = PromptTemplate(
    template="""
    You respond in the language of "{language}", since your responses are given to {language} speakers and they can only understand the language of {language}.
    Search for those image or images only, whose descriptions in a MediaBlock of the 'Response Text' matches
    with the descriptions in the 'Context' data. Output only those image's or images' description from the 
    'Context' data.
    \n{format_instructions}\n'Response Text': {response_text}\n'Context': {context}""",
    input_variables=["response_text","context","language"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    if model_type == "gemini":
        chain = prompt | llm.bind(generation_config={"response_mime_type": "application/json"}) | parser
    else:
        chain = prompt | llm.bind(response_format={"type": "json_object"}) | parser

    img_response = chain.invoke({"response_text": response_text, "context": relevant_doc, "language": language})
    logger.debug(f"img_response is::{img_response}",)
    format_instructions = parser.get_format_instructions()
    logger.debug(f"format_instructions:\n{format_instructions}",)
    logger.debug(f"response_text:\n{response_text}",)

###
    def create_structured_json(img_response):
        result = {}
        for index, img in enumerate(img_response['Image'], start=1):
            logger.debug(f"img: {img}",)
            if img['PageNumber'] is not None:
                # Constructing the key format: "file_name_{filename}_page_{page}_image_{image}"
                image_key = f"FileName {img['FileName']} PageNumber {img['PageNumber']} ImageNumber {img['ImageNumber']}"
                # Add the image key and description to the result dictionary
                result[f"Image{index}"] = image_key
                result[f"Description{index}"] = img['Description']
            else:
                # Constructing the key format: "file_name_{filename}_page_{page}_image_{image}"
                image_key = f"FileName {img['FileName']} SlideNumber {img['SlideNumber']} ImageNumber {img['ImageNumber']}"
                # Add the image key and description to the result dictionary
                result[f"Image{index}"] = image_key
                result[f"Description{index}"] = img['Description']
        
        return json.dumps(result, indent=4)

    # Using the function to transform the data
    structured_response = create_structured_json(img_response)
    logger.debug(structured_response)

    return str(structured_response)

