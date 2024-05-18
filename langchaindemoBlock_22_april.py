from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from operator import itemgetter
from langchain_community.llms import HuggingFaceHub
from langchain.chains import ConversationChain
from langchain_community.chat_models import ChatOpenAI
# from langchain_openai import ChatOpenAI
from langchain.agents import ZeroShotAgent, Tool, AgentExecutor
from langchain.chains.conversation.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from langchain.chains import LLMChain
from langchain.prompts import BaseChatPromptTemplate, PromptTemplate
from langchain.agents import initialize_agent, Tool, load_tools, AgentType
from dotenv import load_dotenv
from openai import OpenAI
from langchain.prompts import PromptTemplate, ChatPromptTemplate, HumanMessagePromptTemplate
from PyPDF2 import PdfReader
from langchain_community.vectorstores import FAISS
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from reportlab.pdfgen import canvas 
import matplotlib
import os
from flask import Flask, render_template, request, session, flash, get_flashed_messages
from io import BytesIO
from semantic_router import Route, RouteLayer
from semantic_router.encoders import OpenAIEncoder
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.chains import ConversationChain
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain.document_loaders import UnstructuredExcelLoader, UnstructuredWordDocumentLoader, UnstructuredPowerPointLoader, TextLoader

load_dotenv(dotenv_path="HUGGINGFACEHUB_API_TOKEN.env")


def RAG(file_content,embeddings,file):
    print("file is:",file)
    
    filename = file.filename
    extension = filename.rsplit('.', 1)[1].lower()
    print("Extension is:",extension)
    raw_text = ''
    if extension=="pdf":
        doc_reader = PdfReader(file_content)

        for i, page in enumerate(doc_reader.pages):
            text = page.extract_text()
            if text:
                raw_text += text

    elif extension=="csv":
        temp_path = os.path.join(filename)
        file.seek(0)
        file.save(temp_path)
        loader = CSVLoader(file_path=temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content + '\n\n' for document in data)
        os.remove(temp_path)

    elif extension=="xlsx" or extension=="xls":
        temp_path = os.path.join(filename)
        file.seek(0)
        file.save(temp_path)
        loader = UnstructuredExcelLoader(temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content + '\n\n' for document in data)
        os.remove(temp_path)

    elif extension=="docx":
        temp_path = os.path.join(filename)
        file.seek(0)
        file.save(temp_path)
        loader = UnstructuredWordDocumentLoader(temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content for document in data)
        os.remove(temp_path)

    elif extension=="pptx":
        temp_path = os.path.join(filename)
        file.seek(0)
        file.save(temp_path)
        loader = UnstructuredPowerPointLoader(temp_path)
        data = loader.load()
        raw_text = raw_text.join(document.page_content for document in data)
        os.remove(temp_path)

    elif extension=="txt":
        print(f"TExt file name is ::{filename}")
        temp_path = os.path.join(filename)
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
    length_function = len,
    )
    # uses openai embeddings for chunking, costs time and money but gives good performances, not ideal for real-time
    # text_splitter = SemanticChunker(OpenAIEmbeddings(), breakpoint_threshold_type="percentile", number_of_chunks= 10000)
    print("Before Embeddings!")
    texts = text_splitter.split_text(raw_text)
    print("Now Doing Embeddings!")
    docsearch = FAISS.from_texts(texts, embeddings)
    print("docsearch made")
    return docsearch

promptSelector = PromptTemplate(
    input_variables=["input_documents","human_input"],
    template="""
    As an educational chatbot, you are tasked with guiding the selection of the most suitable learning scenario 
    tailored to the specific requirements of course content.
    Your decision-making process is 
    informed by evaluating 'Human Input' and 'Input Documents', allowing you to determine the best fit among 
    the following for course development:

    Gamified: A gamified environment that encourages applying subject knowledge to escape a scenario, 
    enhancing investigative and critical thinking skills.
    Linear: Straightforward, step-by-step training on a topic, ending with quizzes to evaluate understanding.
    Branched: A sandbox-style experience where users can explore various aspects of a topic at 
    their own pace, including subtopics with quizzes. 
    Simulation: A decision-making driven gamified learning experience, where choices lead to different 
    outcomes, encouraging exploration of consequences. 

    'Human Input': ({human_input})
    'Input Documents': ({input_documents})
        
    EXAMPLE BOT REPLIES 
    Your reply should be one of the below (Depends on what you find suitable to be selected):
    Bot: Gamified Scenario
    Bot: Simulation Scenario
    Bot: Linear Scenario
    Bot: Branched Scenario
    """
)


prompt_linear = PromptTemplate(
    input_variables=["input_documents","human_input","content_areas","learning_obj"],
    template="""
    You are an educational bot that creates engaging educational content in a Linear Scenario Format using
    a system of blocks. You give step-by-step detail information such that you are teaching a student.

    ***WHAT TO DO***
    To accomplish educational Linear Scenario creation, YOU will:

    1. Take the "Human Input" which represents the content topic or description for which the scenario is to be formulated.
    2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
    and create the scenario according to these very "Learning Objectives" and "Content Areas" specified.
    3. Generate a JSON-formatted in Linear Scenario structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the content efficiently and logically.
    
    'Human Input': {human_input};
    'Input Documents': {input_documents};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};
    ***WHAT TO DO END***

    
    The Linear Scenarios are built using blocks, each having its own parameters.
    Block types include: 
    'TextBlock' with timer(optional), title, and description
    'MediaBlock' with timer(optional), title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
    “You are good at this…”. “You can't do this because...”. Then also give:
    FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    'SelfAssessmentTextBlock' with title, and descritpion(This is part of formative assessment. It is assessment of oneself or one's actions, attitudes, or performance in relation to learning objectives.) 
    'QuestionBlock' with Question text, answers, correct answer, wrong answer message
    'GoalBlock' with Title, Score

    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    Linear Scenario: A type of educational structure in which multiple or single TextBlocks, MediaBlocks and QuestionBlocks will be 
    used to give detailed information to users based on "Learning Objectives", "Content Areas" and "Input Documents". The use of TextBlocks and MediaBlocks actually act as segregating various aspects of the subject matter, by giving information of the various concepts of subject matter in detailed and dedicated way. For each of the concept or aspect of the subject, a detailed information, illustrative elaboration (if needed) and Question are asked for testing. At the end of covering all aspects of the subject, there will be FeedbackAndFeedforwardBlock and SelfAssessmentTextBlock followed by the TestBlocks having series or single QuestionBlock/s to test user's knowledge and GoalBlock for scoring users.
    ***
    ***YOU WILL BE REWARD IF:
    All the TextBlocks in the branches, has valid step-by-step and detailed information of the subject matters such that you are teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
    TextBlocks should provide extremely specific and detailed information so user can get as much knowledge and facts as there is available.
    The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
    user interest is kept. 
    The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
    Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
    so the user uses critical thinking skills and is encouraged to think about how much of the Learning Objectives has been achieved.
    ***
    ***YOU WILL BE PENALISED IF:
    The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
    The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
    ***
    The Example below is just for your concept and do not absolutely produce the same example in your response.
    Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
    You are creative in the manner of choosing the number of TextBlocks, MediaBlocks and QuestionBlocks to give best quality information to students. You are free to choose TextBlocks or MediaBlocks or QuestionBlocks or both or multiple of them to convey best quality, elaborative information.
    Make sure students learn from these TextBlocks and MediaBlocks, and are tested via QuestionBlocks.

    \nOverview structure of the Linear Scenario\n
    ScenarioType
    LearningObjectives
    ContentAreas
    Start
    TextBlock (Welcome message to the scenario and proceedings)
    TextBlock/s (Information elaborated/ subject matter described in detail)
    MediaBlock/s (To give illustrated, complimentary material to elaborate on the information given in Text Blocks. To give such information, that needs illustrated explaination.)
    QuestionBlock/s
    FeedbackAndFeedforwardBlock
    SelfAssessmentTextBlock
    TestBlocks => QuestionBlock/s, GoalBlock
    \nEnd of Overview structure\n

    \n\nEXAMPLE START: LINEAR SCENARIO:\n\n
{{
    "ScenarioType": "Linear Scenario",
    "LearningObjectives": [
        "This mandatory block is where you !Give users single or multiple learning objectives of the Linear Scenario!"
    ],
    "ContentAreas": [
        "This mandatory block is where you !Give users Content Areas of the Linear Scenario single or multiple!"
    ],
    "Start": "Introduction to Renewable Energy",
    "Blocks": [
        {{
            "id": "1",
            "Purpose": "This MANDATORY block (In terms of either one Text Block or multiple per scenario.) is where you !Begin by giving welcome message to the scenario. In further Text Blocks down the example format you use these blocks to give detailed information on every aspect of various subject matters as asked.",
            "type": "Text Block",
            "title": "",
            "description": "You write detailed descriptions here and try your best to educate the students on the subject matter, leaving no details untouched and undescribed"
        }},
        {{
            "id": "2",
            "Purpose": "This OPTIONAL block (In terms of either one Media Block or multiple or no Media Block per scenario. In case of no Media Block, Text Block use is Mandatory to give information about each and every aspect of the subject matter) is where you !Give students an illustrative experience that elaborates on the information given in Text Blocks and are used in a complimentary way to them.",
            "type": "Media Block",
            "title": "",
            "mediaType": "360-image/Image (Preferred)/Video etc",
            "description": "",
            "overlayTags": [
                {{
                    "textTag/imageTag/videoTag": "Explain and teach the students, using these overlayTags, the different aspects of the information for this media block. Also give instructions here of how to shoot these medias, what information are they elaborating based on the information present in Text Blocks."
                }},
                {{
                    "textTag/imageTag/videoTag": ""
                }}
            ]
        }},
        {{
            "id": "3",
            "Purpose": "This OPTIONAL block is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the content and importance at hand",
            "type": "Question Block",
            "questionText": "",
            "answers": [
                "",
                "",
                "",
                ""
            ],
            "correctAnswer": "",
            "wrongAnswerMessage": ""
        }},
        {{
            "id": "4",
            "Purpose": "Mandatory",
            "type": "FeedbackAndFeedforwardBlock",
            "Feedback": "",
            "Feedforward": ""
        }},
        {{
            "id": "5",
            "Purpose": "Mandatory",
            "type": "SelfAssessmentTextBlock",
            "description": ""
        }},
        {{
            "id": "6",
            "TestBlocks": [
                {{
                    "id": "6.1",
                    "Purpose": "This Question Block's status in the 'Test' array here is MANDATORY(Single or Multiple QuestionBlocks) now. This is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the content and importance at hand",
                    "type": "Question Block",
                    "questionText": "",
                    "answers": [
                        "",
                        "",
                        "",
                        ""
                    ],
                    "correctAnswer": "",
                    "wrongAnswerMessage": ""
                }},
                {{
                    "id": "6.2",
                    "type": "Goal Block",
                    "title": "A messsage of confirmation",
                    "score": "Integer number here based on number of questions"
                }}
            ]
        }}
    ]
}}
    \n\nEND OF EXAMPLE\n\n

    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable. 
    Give concise, relevant, clear, and descriptive information as you are an education provider that has expertise 
    in molding asked information into the said block structure to teach the students.     

    NEGATIVE PROMPT: Responding outside the JSON format.   

    Chatbot (Tone of a teacher teaching student in great detail):"""
)




# prompt_gamified_original = PromptTemplate(
#     input_variables=["input_documents","human_input","content_areas","learning_obj"],
#     template="""
#     You are an education course creator that creates engaging courses in a Gamified Scenario Format using
#     a system of blocks. You formulate from the given data, an Escape Room type scenario
#     where you give a story situation to the student to escape from. YOu also give information in the form of
#     clues to the student of the subject matter so that with studying those clues' information the
#     student will be able to escape the situations by making correct choices.

#     ***WHAT TO DO***
#     To accomplish course creation, YOU will:

#     1. Take the "Human Input" which represents the course content topic or description for which the course is to be formulated.
#     2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
#     and create the course according to these very "Learning Objectives" and "Content Areas" specified.
#     3. Generate a JSON-formatted course structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.
    
#     'Human Input': {human_input};
#     'Input Documents': {input_documents};
#     'Learning Objectives': {learning_obj};
#     'Content Areas': {content_areas};
#     ***WHAT TO DO END***

#     The courses are built using blocks, each having its own parameters.
#     Block types include: 
#     'Text Block': with timer, title, and description
#     'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
#     'Branching Block'(includes two types, choose one of the two): 
#     'Simple Branching' with Title, Timer, Proceed To Branch List  
#     'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
#     'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
#     “You are good at this…”. “You can't do this because...”. Then also give:
#     FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    
#     'Goal Block': Title, Score
#     'QuestionBlock' with Question text, answers, correct answer, wrong answer message
#     'Jump Block': with title, Proceed To Block___

#     ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
#     Gamified Scenario: A type of course structure in which multiple or single TextBlocks, MediaBlocks will be used to give clues of information to students. The student after studying these clues will know what Correct Choice to select to ultimately escape-the-room like situation. The choices are given via Branching Blocks (Simple or Conditional). These blocks give users only 2 choices. 1 is Incorrect or Partially-Correct Choice. The other 2nd one is the Correct Choice.
#     The Incorrect Choice leads to Incorrect Branch having 'FeedbackAndFeedforwardBlock' and 'Jump Block'. This 'Jump Block' routes the student back to the Branching Block which offered this Incorrect Choice so user can select the Correct Choice to move forward.
#     The Partially-Correct Choice transitions into a branch called the Partially-Correct Branch, which contains a 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' serves a unique function, directing the user to a point where the storyline can converge seamlessly with the Correct Choice Branch. At this junction, it appears natural to the student that both the Partially-Correct Choice and the Correct Choice lead to the same conclusion. This setup illustrates that while both choices are valid and lead to the desired outcome, one choice may be superior to the other in certain respects.
#     The Correct Choice leads to Correct Branch that has single or multiple number of 'Text Blocks', 'Media Blocks', 'Question Blocks', 'FeedbackAndFeedforwardBlock' and a 'Branching Block' (Simple or Conditional). This Branch progresses the actual story by using the Text and Media Blocks to provide clues of information that help student to select subsequent Correct Choice in the Branching Block and leading the student with each Correct Choice to ultimately escape the room situation and being greeted with a good 'Goal Block' score.
#     ***
#     ***YOU WILL BE REWARD IF:
#     All the TextBlocks in the branches, has valid detailed information in the form of clues of the subject matters such that you are teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
#     TextBlocks should provide extremely specific and detailed information so user can get as much knowledge and facts as there is available.
#     The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
#     user interest is kept. The MediaBlocks visually elaborates, Gives overlayTags that are used by student to click on them and get tons of Clues information to be able to select the Correct Choice when given in the subsequent Branching Blocks. 
#     The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
#     Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
#     so the user uses critical thinking skills and is encouraged to think about how much of the Learning Objectives has been achieved.
#     ***
#     ***YOU WILL BE PENALISED IF:
#     The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
#     The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
#     ***
#     The Example below is just for your concept and do not absolutely produce the same example in your course.
#     Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
#     You are creative in the manner of choosing the number of TextBlocks, MediaBlocks and QuestionBlocks to give best quality information to students. You are free to choose TextBlocks or MediaBlocks or QuestionBlocks or both or multiple of them to convey best quality, elaborative information.
#     Make sure students learn from these TextBlocks and MediaBlocks, and are tested via QuestionBlocks.
#     You are creatively free to choose the placements of Branching Blocks (Simple or Conditional) and you should know that it is mandatory for you to give only 2 Choices, Incorrect or Partially-Correct choice (You Decide) and the Correct Choice (Mandatory).
#     Note that the Incorrect Choice leads to 'FeedbackAndFeedforwardBlock' and 'Jump Block', which will lead the student to the Branching Block that offered this Incorrect Choice.
#     The Partially-Correct Choice leads to the branch with 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' leads to one of the blocks in the Correct Choice branch, seemlessly transitioning story since the Partially-Correct and Correct Choice both has same conclusion but the student gets different Goal Block scores. The Partially-Correct choice Goal Block has less score than if the Correct Choice was selected.
#     You are creatively in terms filling any parameters' values in the Blocks mentioned in the Sample examples below. The Blocks has static parameter names in the left side of the ':'. The right side are the values where you will insert text inside the "" quotation marks. You are free to fill them in the way that is fitting to the course you are creating. 
#     The Sample Examples are only for your concept and you should produce your original values and strings for each of the parameters used in the Blocks. 
    
#     \nOverview structure of the Course\n
#     ScenarioType
#     LearningObjectives
#     ContentAreas
#     Start
#     TextBlock (Welcome to the course)
#     TextBlock/s (Information elaborated/ subject matter described in detail)
#     MediaBlock/s (To give illustrated, complimentary material to elaborate on the information given in Text Blocks. To give such information, that needs illustrated explaination.)
#     QuestionBlock/s
#     FeedbackAndFeedforwardBlock
#     SelfAssessmentTextBlock
#     TestBlocks => QuestionBlock/s, GoalBlock
#     \nEnd of Overview structure\n

#     \n\nSAMPLE EXAMPLE\n\n
# {{
#     "ScenarioType": "Gamified Scenario",
#     "LearningObjectives": [
#         "This mandatory block is where you !Give users single or multiple learning objectives of the course!"
#     ],
#     "ContentAreas": [
#         "This mandatory block is where you !Give users Content Areas of the course single or multiple!"
#     ],
#     "Start": "A course name here",
#     "Blocks": [
#         {{
#             "id": "1",
#             "Purpose": "This block (can be used single or multiple times or None depends on the content to be covered in the course) is where you !Begin by giving welcome message to the course. In further Text Blocks down the course in Branches, you use these blocks to give detailed information on every aspect of various subject matters belonging to each branch. The TextBlocks in branches are used either Single or Multiple Times and are bearers of detailed information and explanations that helps the final course to be produced having an extremely detailed information in it.",
#             "timer": "optional value 00:00 mm:ss, for example 00:30",
#             "type": "Text Block",
#             "title": "Write for every Text Block a fitting title here",
#             "description": "You write detailed descriptions here and try your best to educate the students on the subject matter, leaving no details untouched and undescribed."
#         }},
#         {{
#             "id": "2",
#             "Purpose": "This block (can be used single or multiple times or None  depends on the content to be covered in the Text Blocks relevant to this Media Block) is where you !Give students an illustrative experience that elaborates on the information given in Text Blocks and are used in a complimentary way to them. The media blocks gives great clues using overlayTags",
#             "timer": "optional value 00:00 mm:ss, for example 02:00",
#             "type": "Media Block",
#             "title": "...",
#             "mediaType": "360-image/Image (Preferred)/Video etc",
#             "description": "...",
#             "overlayTags": [
#                 {{
#                     "textTag/imageTag/videoTag": "Explain and teach the students, using these overlayTags, the different aspects of the information for this media block. Also give instructions here of how to shoot these medias, what information are they elaborating based on the information present in Text Blocks. The overlayTags are a great way to give clues to the students to gain valuable information before they are given a choice in the later Branching Block to choose a choice in the story situation. There they will have knowledge gained by these overlayTags at various points in the various branches to help them select the correct choice"
#                 }},
#                 {{
#                     "textTag/imageTag/videoTag": "..."
#                 }}
#             ]
#         }},
#         {{
#             "id": "3",
#             "Purpose": "This block is where you !Divide the course content into ONLY TWO choices, that users can select and the corresponding divided branches leads to a consequence of the choice selected.!",
#             "timer": "optional value 00:00 mm:ss",
#             "type": "Branching Block (Simple Branching)",
#             "title": "...",
#             "branches": {{
#                 "3.1": "text (Partially-Correct Choice or Incorrect Choice)",
#                 "3.2": "text (Correct Choice)",
#         }},
#         {{
#             "id": "3.1",
#             "Purpose": "An Incorrect choice selected moves the user to the Jump Block to route the user back to original Decision point branch or Block 3 Branching Block (Simple Branching) in this example sample",
#             "blocks": [
#             {{
#             "id": "3.1.1",
#             "Purpose": "Mandatory for every branch. In this example it is before Jump Block which is end block for this branch.",
#             "type": "FeedbackAndFeedforwardBlock",
#             "Feedback": "Better to be at slower speed, hence brake would not require immediate application",
#             "Feedforward": "Try to be slower next time"
#             }},
#             {{
#             "id": "3.1.2",
#             "type": "Jump Block",
#             "title": "Reevaluate Your Choices",
#             "proceedToBlock": "3"
#             }}
#         ]}},
#         {{
#             "id": "3.2",
#             "blocks": [
#                 {{
#                     "id": "3.2.1",
#                     "timer": "optional value 00:00 mm:ss",
#                     "type": "Text Block",
#                     "title": "...",
#                     "description": "..."
#                 }},
#                 {{
#                     "id": "3.2.2",
#                     "timer": "optional value 00:00 mm:ss",
#                     "type": "Media Block",
#                     "title": "Waiting at intersection after red light stop",
#                     "mediaType": "Image",
#                     "description": "An image of cars standing at the red light, waiting and preferably turning off the engines while wait is about a minute long. Instructions to produce the image: Take a picture of busy intersection with rows of cars and bikes waiting at red light.",
#                     "overlayTags": [
#                         {{
#                             "textTag": "Keep an eye for yellow light to turn on, there you want to start the engines and get ready to move on. "
#                         }}
#                     ]
#                 }},
#                 {{
#                     "id": "3.2.3",
#                     "Purpose": "Mandatory for every branch. In this example it is before Branching Block which is end block for this branch.",
#                     "type": "FeedbackAndFeedforwardBlock",
#                     "Feedback": "...",
#                     "Feedforward": ""
#                 }},
#                 {{
#                     "id": "3.2.4",
#                     "Purpose": "This block is where you !Divide the course content into ONLY TWO choices, whilst asking a question at the same time. The correct choice leads to a seperate branch while the incorrect or partially-correct choice leads to another story branch or story pathway progressing the story.",   
#                     "timer": "optional value 00:00 mm:ss",
#                     "type": "Branching Block (Conditional Branching)",
#                     "title": "...",
#                     "questionText": "...",
#                     "proceedToBranchForEachAnswer": [
#                         {{
#                             "text": "... (Partially-Correct Choice or Incorrect Choice)",
#                             "proceedToBlock": "3.2.4.1"
#                         }},
#                         {{
#                             "text": "... (Correct Choice)",
#                             "proceedToBlock": "3.2.4.2"
#                         }}
#                     ]
#                 }}
#             ]
#         }},
#         {{
#             "id": "3.2.4.1",
#             "Purpose": "In the case of Partially-Correct choice, this branch includes a Goal Block and a Jump Block(that merges the current branch and story progression with the other correct path branch since both of them have same conclusion as seen below blocks of this very branch)",
#             "blocks": [
#             {{
#                 "id": "3.2.4.1.1",
#                 "type": "Goal Block",
#                 "title": "A messsage of confirmation",
#                 "score": "Integer number here based on number of questions, smaller score then the standard Correct option score"
#             }},
#             {{
#                 "id": "3.2.4.1.2",
#                 "Purpose": "Mandatory for every branch. In this example it is before Jump Block which is end block for this branch.",
#                 "type": "FeedbackAndFeedforwardBlock",
#                 "Feedback": "...",
#                 "Feedforward": "..."
#             }},
#             {{
#                 "id": "3.2.4.1.3",
#                 "Purpose": "A Partially-Correct choice leads the story to merge with the Correct choice branch or story path, but the difference is that it merges by giving user the Score less than if the correct path chosen."
#                 "type": "Jump Block",
#                 "title": "...",
#                 "proceedToBlock": "3.2.4.2.2"
#             }}
#             ]
#         }},
#         {{
#             "id": "3.2.4.2",
#             "blocks": [
#                 {{
#                     "id": "3.2.4.2.1",
#                     "timer": "optional value 00:00 mm:ss",
#                     "type": "Text Block",
#                     "title": "...",
#                     "description": "..."
#                 }},
#                 {{
#                     "id": "3.2.4.2.2",
#                     "Purpose": "This Question Block (Single or Multiple QuestionBlocks) is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the course content and importance at hand",
#                     "type": "Question Block",
#                     "questionText": "...",
#                     "answers": [
#                         "...",
#                         "...",
#                         "...",
#                         "..."
#                     ],
#                     "correctAnswer": "...",
#                     "wrongAnswerMessage": "..."
#                 }},
#                 {{
#                     "id": "3.2.4.2.3",
#                     "Purpose": "Mandatory for every branch. In this example it is before Branching Block which is end block for this branch.",
#                     "type": "FeedbackAndFeedforwardBlock",
#                     "Feedback": "...",
#                     "Feedforward": "..."
#                 }},
#                 {{
#                     "id": "3.2.4.2.4",
#                     "Purpose": "This block is where you !Divide the course content into ONLY TWO choices, that users can select and the corresponding divided branches leads to a consequence of the choice selected.!",
#                     "timer": "optional value 00:00 mm:ss",
#                     "type": "Branching Block (Simple Branching)",
#                     "title": "...",
#                     "branches": {{
#                         "3.2.4.2.4.1": "text (Partially-Correct Choice or Incorrect Choice)",
#                         "3.2.4.2.4.2": "text (Correct Choice)",
#                 }},
#                 {{
#                     "id": "3.2.4.2.4.1",
#                     "Purpose": "An Incorrect choice selected moves the user to the Jump Block to route the user back to original Decision point branch or Block 3 Branching Block (Simple Branching) in this example sample",
#                     "blocks": [
#                     {{
#                         "id": "3.2.4.2.4.1.1",
#                         "Purpose": "Mandatory for every branch. In this example it is before Jump block which is end block for this branch.",
#                         "type": "FeedbackAndFeedforwardBlock",
#                         "Feedback": "...",
#                         "Feedforward": "..."
#                     }},
#                     {{
#                     "id": "3.2.4.2.4.1.2",
#                     "type": "Jump Block",
#                     "title": "Reevaluate Your Choices",
#                     "proceedToBlock": "3.2.4"
#                 }}]}},
#                 {{
#                 "id": "3.2.4.2.4.2",
#                 "blocks": [
#                 {{
#                     "id": "3.2.4.2.4.2.1",
#                     "timer": "optional value 00:00 mm:ss",
#                     "type": "Text Block",
#                     "title": "...",
#                     "description": "..."
#                 }},
#                 {{
#                     "id": "3.2.4.2.4.2.2",
#                     "Purpose": "Mandatory for every branch. In this example it is before Goal block which is end block for this branch.",
#                     "type": "FeedbackAndFeedforwardBlock",
#                     "Feedback": "...",
#                     "Feedforward": "..."
#                 }},
#                 {{
#                     "id": "3.2.4.2.4.2.3",
#                     "type": "Goal Block",
#                     "title": "A messsage of conclusion of scenario here fits this block's placement here",
#                     "score": "Integer number here"
#                 }}
#             ]
#         }}
#     ]
# }} 
#     \n\nEND OF SAMPLE EXAMPLE\n\n
#     The SAMPLE EXAMPLE's structure of blocks connection is:
#     1(Text Block) -> 2 (Media Block)
#     2(Media Block) -> 3 (Branching Block (Simple Branching))
#     3 (Branching Block (Simple Branching)) -> |InCorrect Choice| 3.1 
#     3 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2
#     3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock) 
#     3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
#     3.1.2 (Jump Block) -> 3 (Branching Block (Simple Branching))
#     3.2 -> 3.2.1 (Text Block)
#     3.2.1 (Text Block) -> 3.2.2 (Media Block)
#     3.2.2 (Media Block) -> 3.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4 (Branching Block (Conditional Branching))
#     3.2.4 (Branching Block (Conditional Branching)) -> |Partially-Correct Choice| 3.2.4.1
#     3.2.4 (Branching Block (Conditional Branching)) -> |Correct Choice| 3.2.4.2
#     3.2.4.1 -> 3.2.4.1.1 (Goal Block)
#     3.2.4.1.1 (Goal Block) -> 3.2.4.1.2 (FeedbackAndFeedforwardBlock)
#     3.2.4.1.2 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.1.3
#     3.2.4.1.3 (Jump Block) -> 3.2.4.2.2 (Question Block)
#     3.2.4.2 -> 3.2.4.2.1 (Text Block)
#     3.2.4.2.1 (Text Block) -> 3.2.4.2.2 (Question Block)
#     3.2.4.2.2 (Question Block) -> 3.2.4.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4 (Branching Block (Simple Branching))
#     3.2.4.2.4 (Branching Block (Simple Branching)) -> |Incorrect Choice| 3.2.4.2.4.1
#     3.2.4.2.4 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2.4.2.4.2
#     3.2.4.2.4.1 -> 3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.2.4.1.2
#     3.2.4.2.4.1.2 (Jump Block) -> 3.2.4 (Branching Block (Conditional Branching))
#     3.2.4.2.4.2 -> 3.2.4.2.4.2.1 (Text Block)
#     3.2.4.2.4.2.1 (Text Block) -> 3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4.2.3 (Goal Block)

#     ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Media Block)
#     3 (Media Block) -> 4 (Branching Block (Simple Branching))
#     4 (Branching Block (Simple Branching)) -> |Partially-Correct choice| 4.1 
#     4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2
#     4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
#     4.1.1 (FeedbackAndFeedforwardBlock) -> 4.1.2 (Goal Block)
#     4.1.2 (Goal Block) -> |Jump Block| 4.1.2 
#     4.1.2 (Jump Block) -> 4.2.3 (Branching Block (Simple Branching))
#     4.2 -> 4.2.1 (Media Block)
#     4.2.1 (Media Block) -> 4.2.2 (Question Block)
#     4.2.2 (Question Block) -> 4.2.3 (FeedbackAndFeedforwardBlock)
#     4.2.3 (FeedbackAndFeedforwardBlock) -> 4.2.4 (Branching Block (Simple Branching))
#     4.2.4 (Branching Block (Simple Branching)) -> |Incorrect choice| 4.2.4.1
#     4.2.4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2.4.2
#     4.2.4.1 -> 4.2.4.1.1 (FeedbackAndFeedforwardBlock) 
#     4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.2.4.1.2
#     4.2.4.1.2 (Jump Block) -> 4.2.4 (Branching Block (Simple Branching))
#     4.2.4.2 -> 4.2.4.2.1 (Media Block)
#     4.2.4.2.1 (Media Block) -> 4.2.4.2.2 (FeedbackAndFeedforwardBlock) 
#     4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.4.2.3 (Goal Block)

#     AND ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Media Block)
#     3 (Media Block) -> 4 (Branching Block (Conditional Branching))
#     4 (Branching Block (Conditional Branching)) -> |Incorrect choice| 4.1 
#     4 (Branching Block (Conditional Branching)) -> |Correct choice| 4.2
#     4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
#     4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.1.2
#     4.1.2 (Jump Block) -> 4 (Branching Block (Conditional Branching))
#     4.2 -> 4.2.1 (Text Block)
#     4.2.1 (Text Block) -> 4.2.2 (FeedbackAndFeedforwardBlock)
#     4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.3 (Goal Block)

#     AND AN ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Branching Block (Conditional Branching))
#     3 (Branching Block (Conditional Branching)) -> |Incorrect choice| 3.1 
#     3 (Branching Block (Conditional Branching)) -> |Correct choice| 3.2
#     3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock)
#     3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
#     3.1.2 (Jump Block) -> 3 (Branching Block (Conditional Branching))
#     3.2 -> 3.2.1 (Text Block)
#     3.2.1 (Text Block) -> 3.2.2 (Media Block)
#     3.2.2 (Media Block) -> 3.2.3 (Question Block)
#     3.2.3 (Question Block) -> 3.2.4 (Question Block)
#     3.2.4 (Question Block) -> 3.2.5 (Question Block)
#     3.2.5 (Question Block) -> 3.2.6 (FeedbackAndFeedforwardBlock)
#     3.2.6 (FeedbackAndFeedforwardBlock) -> 3.2.7 (Branching Block (Simple Branching))
#     3.2.7 (Branching Block (Simple Branching)) -> |Incorrect choice| 3.2.7.1
#     3.2.7 (Branching Block (Simple Branching)) -> |Correct choice| 3.2.7.2
#     3.2.7.1 -> 3.2.7.1.1 (FeedbackAndFeedforwardBlock)
#     3.2.7.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.7.1.2
#     3.2.7.1.2 (Jump Block) -> 3.2.7 (Branching Block (Simple Branching))
#     3.2.7.2 ->  3.2.7.2.1 (Text Block)
#     3.2.7.2.1 (Text Block) -> 3.2.7.2.2 (Text Block)
#     3.2.7.2.2 (Text Block) -> 3.2.7.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.7.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.7.2.4 (Goal Block)

#     The input paramters according to which you will be making the course:
#     'Human Input': {human_input};
#     'Input Documents': {input_documents};
#     'Learning Objectives': {learning_obj};
#     'Content Areas': {content_areas};
    
#     !!!ATTENTION!!!
#     Please note that you absolutely should not give response anything else outside the JSON format since
#     human will be using the generated code directly into the server side to run the JSON code.
#     Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
#     and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
#     to be compilable.  
#     Give concise, relevant, clear, and descriptive instructions as you are a course creator that has expertise 
#     in molding asked information into the Gamified scenario structure.

#     NEGATIVE PROMPT: Do not respond outside the JSON format.     
    
#     Chatbot:"""
# )

#created for responding a meta-data knowledge twisted to meet escape room scene
prompt_gamified_setup = PromptTemplate(
    input_variables=["input_documents","human_input","content_areas","learning_obj"],
    template="""
    Show the answer to human's input step-by-step such that you are teaching a student. 
    The teaching should be clear, and give extremely detailed descriptions covering all aspects of the information provided to you in INPUT PARAMETERS,
    without missing or overlooking any information.
    
    INPUT PARAMETERS:
    'Human Input': {human_input};
    'Input Documents': {input_documents};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};
    Chatbot:"""
)

# prompt_gamified_simple = PromptTemplate(
#     input_variables=["response_of_bot_simple","human_input","content_areas","learning_obj"],
#     template="""
#     You are a Bot in the Education field that creates engaging Gamified Scenarios using a Format of
#     a system of blocks. You formulate from the given data, an Escape Room type scenario
#     where you give a story situation to the student to escape from. YOu also give information in the form of
#     clues to the student of the subject matter so that with studying those clues' information the
#     student will be able to escape the situations by making correct choices.

#     ***WHAT TO DO***
#     To accomplish scenario creation, YOU will:

#     1. Take the "Human Input" which represents the course content topic or description for which the course is to be formulated.
#     2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
#     and create the scenario according to these very "Learning Objectives" and "Content Areas" specified.
   
#     'Human Input': {human_input};
#     'Input Documents': {response_of_bot_simple};
#     'Learning Objectives': {learning_obj};
#     'Content Areas': {content_areas};
#     ***WHAT TO DO END***

#     The Gamified Scenario is built using blocks, each having its own parameters.
#     Block types include: 
#     'Text Block': with timer, title, and description
#     'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
#     'Branching Block'(includes two types, choose one of the two): 
#     'Simple Branching' with Title, Timer, Proceed To Branch List  
#     'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
#     'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
#     “You are good at this…”. “You can't do this because...”. Then also give:
#     FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    
#     'Goal Block': Title, Score
#     'QuestionBlock' with Question text, answers, correct answer, wrong answer message
#     'Jump Block': with title, Proceed To Block___

#     ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
#     Gamified Scenario: A type of course structure in which multiple or single TextBlocks, MediaBlocks will be used to give clues of information to students. The student after studying these clues will know what Correct Choice to select to ultimately escape-the-room like situation. The choices are given via Branching Blocks (Simple or Conditional). These blocks give users only 2 choices. 1 is Incorrect or Partially-Correct Choice. The other 2nd one is the Correct Choice.
#     The Incorrect Choice leads to Incorrect Branch having 'FeedbackAndFeedforwardBlock' and 'Jump Block'. This 'Jump Block' routes the student back to the Branching Block which offered this Incorrect Choice so user can select the Correct Choice to move forward.
#     The Partially-Correct Choice transitions into a branch called the Partially-Correct Branch, which contains a 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' serves a unique function, directing the user to a point where the storyline can converge seamlessly with the Correct Choice Branch. At this junction, it appears natural to the student that both the Partially-Correct Choice and the Correct Choice lead to the same conclusion. This setup illustrates that while both choices are valid and lead to the desired outcome, one choice may be superior to the other in certain respects.
#     The Correct Choice leads to Correct Branch that has single or multiple number of 'Text Blocks', 'Media Blocks', 'Question Blocks', 'FeedbackAndFeedforwardBlock' and a 'Branching Block' (Simple or Conditional). This Branch progresses the actual story by using the Text and Media Blocks to provide clues of information that help student to select subsequent Correct Choice in the Branching Block and leading the student with each Correct Choice to ultimately escape the room situation and being greeted with a good 'Goal Block' score.
#     ***
#     ***YOU WILL BE REWARD IF:
#     All the TextBlocks in the branches, has valid detailed information in the form of clues of the subject matters such that you are teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
#     TextBlocks should provide extremely specific and detailed information so user can get as much knowledge and facts as there is available.
#     The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
#     user interest is kept. The MediaBlocks visually elaborates, Gives overlayTags that are used by student to click on them and get tons of Clues information to be able to select the Correct Choice when given in the subsequent Branching Blocks. 
#     The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
#     Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
#     so the user uses critical thinking skills and is encouraged to think about how much of the Learning Objectives has been achieved.
#     ***
#     ***YOU WILL BE PENALISED IF:
#     The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
#     The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
#     ***
#     The Example below is just for your concept and do not absolutely produce the same example in your Gamified scenario.
#     Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
#     You are creative in the manner of choosing the number of TextBlocks, MediaBlocks and QuestionBlocks to give best quality information to students. You are free to choose TextBlocks or MediaBlocks or QuestionBlocks or both or multiple of them to convey best quality, elaborative information.
#     Make sure students learn from these TextBlocks and MediaBlocks, and are tested via QuestionBlocks.
#     You are creatively free to choose the placements of Branching Blocks (Simple or Conditional) and you should know that it is mandatory for you to give only 2 Choices, Incorrect or Partially-Correct choice (You Decide) and the Correct Choice (Mandatory).
#     Note that the Incorrect Choice leads to 'FeedbackAndFeedforwardBlock' and 'Jump Block', which will lead the student to the Branching Block that offered this Incorrect Choice.
#     The Partially-Correct Choice leads to the branch with 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' leads to one of the blocks in the Correct Choice branch, seemlessly transitioning story since the Partially-Correct and Correct Choice both has same conclusion but the student gets different Goal Block scores. The Partially-Correct choice Goal Block has less score than if the Correct Choice was selected.
#     You are creatively in terms filling any parameters' values in the Blocks mentioned in the Sample examples below. The Blocks has static parameter names in the left side of the ':'. The right side are the values where you will insert text inside the "" quotation marks. You are free to fill them in the way that is fitting to the course you are creating. 
#     The Sample Examples are only for your concept and you should produce your original values and strings for each of the parameters used in the Blocks. 
    
#     The SAMPLE EXAMPLE structure of blocks connection is (Remember to Fill out the Blocks' Parameters with details. This is just structure overview here):
#     1(Text Block) -> 2 (Media Block)
#     2(Media Block) -> 3 (Branching Block (Simple Branching))
#     3 (Branching Block (Simple Branching)) -> |InCorrect Choice| 3.1 
#     3 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2
#     3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock) 
#     3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
#     3.1.2 (Jump Block) -> 3 (Branching Block (Simple Branching))
#     3.2 -> 3.2.1 (Text Block)
#     3.2.1 (Text Block) -> 3.2.2 (Media Block)
#     3.2.2 (Media Block) -> 3.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4 (Branching Block (Conditional Branching))
#     3.2.4 (Branching Block (Conditional Branching)) -> |Partially-Correct Choice| 3.2.4.1
#     3.2.4 (Branching Block (Conditional Branching)) -> |Correct Choice| 3.2.4.2
#     3.2.4.1 -> 3.2.4.1.1 (Goal Block)
#     3.2.4.1.1 (Goal Block) -> 3.2.4.1.2 (FeedbackAndFeedforwardBlock)
#     3.2.4.1.2 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.1.3
#     3.2.4.1.3 (Jump Block) -> 3.2.4.2.2 (Question Block)
#     3.2.4.2 -> 3.2.4.2.1 (Text Block)
#     3.2.4.2.1 (Text Block) -> 3.2.4.2.2 (Question Block)
#     3.2.4.2.2 (Question Block) -> 3.2.4.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4 (Branching Block (Simple Branching))
#     3.2.4.2.4 (Branching Block (Simple Branching)) -> |Incorrect Choice| 3.2.4.2.4.1
#     3.2.4.2.4 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2.4.2.4.2
#     3.2.4.2.4.1 -> 3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.2.4.1.2
#     3.2.4.2.4.1.2 (Jump Block) -> 3.2.4 (Branching Block (Conditional Branching))
#     3.2.4.2.4.2 -> 3.2.4.2.4.2.1 (Text Block)
#     3.2.4.2.4.2.1 (Text Block) -> 3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4.2.3 (Goal Block)

#     ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Media Block)
#     3 (Media Block) -> 4 (Branching Block (Simple Branching))
#     4 (Branching Block (Simple Branching)) -> |Partially-Correct choice| 4.1 
#     4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2
#     4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
#     4.1.1 (FeedbackAndFeedforwardBlock) -> 4.1.2 (Goal Block)
#     4.1.2 (Goal Block) -> |Jump Block| 4.1.2 
#     4.1.2 (Jump Block) -> 4.2.3 (Branching Block (Simple Branching))
#     4.2 -> 4.2.1 (Media Block)
#     4.2.1 (Media Block) -> 4.2.2 (Question Block)
#     4.2.2 (Question Block) -> 4.2.3 (FeedbackAndFeedforwardBlock)
#     4.2.3 (FeedbackAndFeedforwardBlock) -> 4.2.4 (Branching Block (Simple Branching))
#     4.2.4 (Branching Block (Simple Branching)) -> |Incorrect choice| 4.2.4.1
#     4.2.4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2.4.2
#     4.2.4.1 -> 4.2.4.1.1 (FeedbackAndFeedforwardBlock) 
#     4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.2.4.1.2
#     4.2.4.1.2 (Jump Block) -> 4.2.4 (Branching Block (Simple Branching))
#     4.2.4.2 -> 4.2.4.2.1 (Media Block)
#     4.2.4.2.1 (Media Block) -> 4.2.4.2.2 (FeedbackAndFeedforwardBlock) 
#     4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.4.2.3 (Goal Block)

#     AND ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Media Block)
#     3 (Media Block) -> 4 (Branching Block (Conditional Branching))
#     4 (Branching Block (Conditional Branching)) -> |Incorrect choice| 4.1 
#     4 (Branching Block (Conditional Branching)) -> |Correct choice| 4.2
#     4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
#     4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.1.2
#     4.1.2 (Jump Block) -> 4 (Branching Block (Conditional Branching))
#     4.2 -> 4.2.1 (Text Block)
#     4.2.1 (Text Block) -> 4.2.2 (FeedbackAndFeedforwardBlock)
#     4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.3 (Goal Block)

#     AND AN ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Branching Block (Conditional Branching))
#     3 (Branching Block (Conditional Branching)) -> |Incorrect choice| 3.1 
#     3 (Branching Block (Conditional Branching)) -> |Correct choice| 3.2
#     3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock)
#     3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
#     3.1.2 (Jump Block) -> 3 (Branching Block (Conditional Branching))
#     3.2 -> 3.2.1 (Text Block)
#     3.2.1 (Text Block) -> 3.2.2 (Media Block)
#     3.2.2 (Media Block) -> 3.2.3 (Question Block)
#     3.2.3 (Question Block) -> 3.2.4 (Question Block)
#     3.2.4 (Question Block) -> 3.2.5 (Question Block)
#     3.2.5 (Question Block) -> 3.2.6 (FeedbackAndFeedforwardBlock)
#     3.2.6 (FeedbackAndFeedforwardBlock) -> 3.2.7 (Branching Block (Simple Branching))
#     3.2.7 (Branching Block (Simple Branching)) -> |Incorrect choice| 3.2.7.1
#     3.2.7 (Branching Block (Simple Branching)) -> |Correct choice| 3.2.7.2
#     3.2.7.1 -> 3.2.7.1.1 (FeedbackAndFeedforwardBlock)
#     3.2.7.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.7.1.2
#     3.2.7.1.2 (Jump Block) -> 3.2.7 (Branching Block (Simple Branching))
#     3.2.7.2 ->  3.2.7.2.1 (Text Block)
#     3.2.7.2.1 (Text Block) -> 3.2.7.2.2 (Text Block)
#     3.2.7.2.2 (Text Block) -> 3.2.7.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.7.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.7.2.4 (Goal Block)
    
#     !!!WARNING!!!
#     Always give a complete response of the whole scenario since your response will be used in a
#     non-conversational chatbot environment where no conversations and interaction between the chatbot
#     and human takes place, so you need to absolutely provide a complete Gamified scenario response
#     encompassing the fullfillment of every need available.
#     !!!WARNING_END!!!
#     Chatbot:"""
# )

# prompt_gamified_simple = PromptTemplate(
#     input_variables=["response_of_bot_simple","human_input","content_areas","learning_obj"],
#     template="""
#     You are a Bot in the Education field that creates engaging Gamified Scenarios using a Format of
#     a system of blocks. You formulate from the given data, an Escape Room type scenario
#     where you give a story situation to the student to escape from. YOu also give information in the form of
#     clues to the student of the subject matter so that with studying those clues' information the
#     student will be able to escape the situations by making correct choices.

#     ***WHAT TO DO***
#     To accomplish scenario creation, YOU will:

#     1. Take the "Human Input" which represents the course content topic or description for which the course is to be formulated.
#     2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
#     and create the scenario according to these very "Learning Objectives" and "Content Areas" specified.
#     3. Output your structured response in Mermaid Code Flowchart.

#     'Human Input': {human_input};
#     'Input Documents': {response_of_bot_simple};
#     'Learning Objectives': {learning_obj};
#     'Content Areas': {content_areas};
#     ***WHAT TO DO END***

#     The Gamified Scenario is built using blocks, each having its own parameters.
#     Block types include: 
#     'Text Block': with timer, title, and description
#     'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
#     'Branching Block'(includes two types, choose one of the two): 
#     'Simple Branching' with Title, Timer, Proceed To Branch List  
#     'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
#     'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
#     “You are good at this…”. “You can't do this because...”. Then also give:
#     FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    
#     'Goal Block': Title, Score
#     'QuestionBlock' with Question text, answers, correct answer, wrong answer message
#     'Jump Block': with title, Proceed To Block___

#     ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
#     Gamified Scenario: A type of course structure in which multiple or single TextBlocks, MediaBlocks will be used to give clues of information to students. The student after studying these clues will know what Correct Choice to select to ultimately escape-the-room like situation. The choices are given via Branching Blocks (Simple or Conditional). These blocks give users only 2 choices. 1 is a Incorrect or Partially-Correct Choice. The other 2nd one is the Correct Choice.
#     The Incorrect Choice leads to Incorrect Branch having 'FeedbackAndFeedforwardBlock' and 'Jump Block'. This 'Jump Block' routes the student back to the Branching Block which offered this Incorrect Choice so user can select the Correct Choice to move forward.
#     The Partially-Correct Choice transitions into a branch called the Partially-Correct Branch, which contains a 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' serves a unique function, directing the user to a point where the storyline can converge seamlessly with the Correct Choice Branch. At this junction, it appears natural to the student that both the Partially-Correct Choice and the Correct Choice lead to the same conclusion. This setup illustrates that while both choices are valid and lead to the desired outcome, one choice may be superior to the other in certain respects.
#     The Correct Choice leads to Correct Branch that has single or multiple number of 'Text Blocks', 'Media Blocks', 'Question Blocks', 'FeedbackAndFeedforwardBlock' and a 'Branching Block' (Simple or Conditional). This Branch progresses the actual story by using the Text and Media Blocks to provide clues of information that help student to select subsequent Correct Choice in the Branching Block and leading the student with each Correct Choice to ultimately escape the room situation and being greeted with a good 'Goal Block' score.
#     WHENEVER YOU GIVE A CHOICE, SPECIFIY WITH THAT CHOICE IN SMALL BRACKETS IF IT IS A CORRECT, INCORRECT OR PARTIALLY-CORRECT CHOICE!
#     ***
#     ***YOU WILL BE REWARD IF:
#     All the TextBlocks in the branches, has valid detailed information in the form of clues of the subject matters such that you are teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
#     TextBlocks should provide extremely specific and detailed information so user can get as much knowledge and facts as there is available.
#     The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
#     user interest is kept. The MediaBlocks visually elaborates, Gives overlayTags that are used by student to click on them and get tons of Clues information to be able to select the Correct Choice when given in the subsequent Branching Blocks. 
#     The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
#     Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
#     so the user uses critical thinking skills and is encouraged to think about how much of the Learning Objectives has been achieved.
#     ***
#     ***YOU WILL BE PENALISED IF:
#     The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
#     The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
#     ***
#     The Example below is just for your concept and do not absolutely produce the same example in your Gamified scenario.
#     Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
#     You are creative in the manner of choosing the number of TextBlocks, MediaBlocks and QuestionBlocks to give best quality information to students. You are free to choose TextBlocks or MediaBlocks or QuestionBlocks or both or multiple of them to convey best quality, elaborative information.
#     Make sure students learn from these TextBlocks and MediaBlocks, and are tested via QuestionBlocks.
#     You are creatively free to choose the placements of Branching Blocks (Simple or Conditional) and you should know that it is mandatory for you to give only 2 Choices, Incorrect or Partially-Correct choice (You Decide) and the Correct Choice (Mandatory).
#     Note that the Incorrect Choice leads to 'FeedbackAndFeedforwardBlock' and 'Jump Block', which will lead the student to the Branching Block that offered this Incorrect Choice.
#     The Partially-Correct Choice leads to the branch with 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' leads to one of the blocks in the Correct Choice branch, seemlessly transitioning story since the Partially-Correct and Correct Choice both has same conclusion but the student gets different Goal Block scores. The Partially-Correct choice Goal Block has less score than if the Correct Choice was selected.
#     You are creatively in terms filling any parameters' values in the Blocks mentioned in the Sample examples below. The Blocks has static parameter names in the left side of the ':'. The right side are the values where you will insert text inside the "" quotation marks. You are free to fill them in the way that is fitting to the course you are creating. 
#     The Sample Examples are only for your concept and you should produce your original values and strings for each of the parameters used in the Blocks. 
    
#     The SAMPLE EXAMPLE structure of blocks connection is (Remember to Fill out the Blocks' Parameters with details. This is just structure overview here):
#     1(Text Block) -> 2 (Media Block)
#     2(Media Block) -> 3 (Branching Block (Simple Branching))
#     3 (Branching Block (Simple Branching)) -> |InCorrect Choice| 3.1 
#     3 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2
#     3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock) 
#     3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
#     3.1.2 (Jump Block) -> 3 (Branching Block (Simple Branching))
#     3.2 -> 3.2.1 (Text Block)
#     3.2.1 (Text Block) -> 3.2.2 (Media Block)
#     3.2.2 (Media Block) -> 3.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4 (Branching Block (Conditional Branching))
#     3.2.4 (Branching Block (Conditional Branching)) -> |Partially-Correct Choice| 3.2.4.1
#     3.2.4 (Branching Block (Conditional Branching)) -> |Correct Choice| 3.2.4.2
#     3.2.4.1 -> 3.2.4.1.1 (Goal Block)
#     3.2.4.1.1 (Goal Block) -> 3.2.4.1.2 (FeedbackAndFeedforwardBlock)
#     3.2.4.1.2 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.1.3
#     3.2.4.1.3 (Jump Block) -> 3.2.4.2.2 (Question Block)
#     3.2.4.2 -> 3.2.4.2.1 (Text Block)
#     3.2.4.2.1 (Text Block) -> 3.2.4.2.2 (Question Block)
#     3.2.4.2.2 (Question Block) -> 3.2.4.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4 (Branching Block (Simple Branching))
#     3.2.4.2.4 (Branching Block (Simple Branching)) -> |Incorrect Choice| 3.2.4.2.4.1
#     3.2.4.2.4 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2.4.2.4.2
#     3.2.4.2.4.1 -> 3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.2.4.1.2
#     3.2.4.2.4.1.2 (Jump Block) -> 3.2.4 (Branching Block (Conditional Branching))
#     3.2.4.2.4.2 -> 3.2.4.2.4.2.1 (Text Block)
#     3.2.4.2.4.2.1 (Text Block) -> 3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock)
#     3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4.2.3 (Goal Block)

#     ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Media Block)
#     3 (Media Block) -> 4 (Branching Block (Simple Branching))
#     4 (Branching Block (Simple Branching)) -> |Partially-Correct choice| 4.1 
#     4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2
#     4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
#     4.1.1 (FeedbackAndFeedforwardBlock) -> 4.1.2 (Goal Block)
#     4.1.2 (Goal Block) -> |Jump Block| 4.1.2 
#     4.1.2 (Jump Block) -> 4.2.3 (Branching Block (Simple Branching))
#     4.2 -> 4.2.1 (Media Block)
#     4.2.1 (Media Block) -> 4.2.2 (Question Block)
#     4.2.2 (Question Block) -> 4.2.3 (FeedbackAndFeedforwardBlock)
#     4.2.3 (FeedbackAndFeedforwardBlock) -> 4.2.4 (Branching Block (Simple Branching))
#     4.2.4 (Branching Block (Simple Branching)) -> |Incorrect choice| 4.2.4.1
#     4.2.4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2.4.2
#     4.2.4.1 -> 4.2.4.1.1 (FeedbackAndFeedforwardBlock) 
#     4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.2.4.1.2
#     4.2.4.1.2 (Jump Block) -> 4.2.4 (Branching Block (Simple Branching))
#     4.2.4.2 -> 4.2.4.2.1 (Media Block)
#     4.2.4.2.1 (Media Block) -> 4.2.4.2.2 (FeedbackAndFeedforwardBlock) 
#     4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.4.2.3 (Goal Block)

#     AND ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Media Block)
#     3 (Media Block) -> 4 (Branching Block (Conditional Branching))
#     4 (Branching Block (Conditional Branching)) -> |Incorrect choice| 4.1 
#     4 (Branching Block (Conditional Branching)) -> |Correct choice| 4.2
#     4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
#     4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.1.2
#     4.1.2 (Jump Block) -> 4 (Branching Block (Conditional Branching))
#     4.2 -> 4.2.1 (Text Block)
#     4.2.1 (Text Block) -> 4.2.2 (FeedbackAndFeedforwardBlock)
#     4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.3 (Goal Block)

#     AND AN ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
#     1 (Text Block) -> 2 (Text Block)
#     2 (Text Block) -> 3 (Branching Block (Conditional Branching))
#     3 (Branching Block (Conditional Branching)) -> |Incorrect choice| 3.1 
#     3 (Branching Block (Conditional Branching)) -> |Correct choice| 3.2
#     3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock)
#     3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
#     3.1.2 (Jump Block) -> 3 (Branching Block (Conditional Branching))
#     3.2 -> 3.2.1 (Text Block)
#     3.2.1 (Text Block) -> 3.2.2 (Media Block)
#     3.2.2 (Media Block) -> 3.2.3 (Question Block)
#     3.2.3 (Question Block) -> 3.2.4 (Question Block)
#     3.2.4 (Question Block) -> 3.2.5 (Question Block)
#     3.2.5 (Question Block) -> 3.2.6 (FeedbackAndFeedforwardBlock)
#     3.2.6 (FeedbackAndFeedforwardBlock) -> 3.2.7 (Branching Block (Simple Branching))
#     3.2.7 (Branching Block (Simple Branching)) -> |Incorrect choice| 3.2.7.1
#     3.2.7 (Branching Block (Simple Branching)) -> |Correct choice| 3.2.7.2
#     3.2.7.1 -> 3.2.7.1.1 (FeedbackAndFeedforwardBlock)
#     3.2.7.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.7.1.2
#     3.2.7.1.2 (Jump Block) -> 3.2.7 (Branching Block (Simple Branching))
#     3.2.7.2 ->  3.2.7.2.1 (Text Block)
#     3.2.7.2.1 (Text Block) -> 3.2.7.2.2 (Text Block)
#     3.2.7.2.2 (Text Block) -> 3.2.7.2.3 (FeedbackAndFeedforwardBlock)
#     3.2.7.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.7.2.4 (Goal Block)
    
#     Your MERMAID code response can look like this for each block (It will compile when you for each block you avoid parenthesis of {{ and [ types and avoid " commas):
#     flowchart TD
#     A(
#             id:2,
#             type: Media Block, 
#             title: Identifying Your Resources,
#             mediaType: 360-image,
#             description: A 360-degree view of your surroundings in the forest. You can see various materials that could be useful for starting a fire.,
#             overlayTags:      
#                     textTag: Dry Leaves - Potential tinder.,
#                     textTag: Twigs and Branches - Small and medium-sized for kindling.,
#                     textTag: Large Logs - For sustaining the fire once started.
#     )

#     So make the mermaid flowchart of the above json reply of yours please.

#     Also remember where jumpblocks and branchingblocks takes the flowchart to. 

#     A complete Mermaid Code Response would have Blocks defined first and then the Interconnection written
#     after when all the Blocks having their complete paramters and values defined!

#     !!!WARNING!!!
#     Always give a complete response of the whole scenario since your response will be used in a
#     non-conversational chatbot environment where no conversations and interaction between the chatbot
#     and human takes place, so you need to absolutely provide a complete Gamified scenario response
#     encompassing the fullfillment of every need available.
#     !!!WARNING_END!!!
#     Chatbot:"""
# )

prompt_gamified_json = PromptTemplate(
    input_variables=["response_of_bot","human_input","content_areas","learning_obj"],
    template="""
    You are a Bot in the Education field that creates engaging Gamified Scenarios using a Format of
    a system of blocks. You formulate from the given data, an Escape Room type scenario
    where you give a story situation to the student to escape from. YOu also give information in the form of
    clues to the student of the subject matter so that with studying those clues' information the
    student will be able to escape the situations by making correct choices. This type of game is
    also known as Exit Game and you are tasked with making Exit Game Scenarios.

    ***WHAT TO DO***
    To accomplish Exit Game creation, YOU will:

    1. Take the "Human Input" which represents the Exit Game content topic or description for which the Exit Game is to be formulated.
    2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
    and create the Exit Game according to these very "Learning Objectives" and "Content Areas" specified.
    3. Generate a JSON-formatted Exit Game structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.
    
    'Human Input': {human_input};
    'Input Documents': {response_of_bot};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};
    ***WHAT TO DO END***

    The Exit Game are built using blocks, each having its own parameters.
    Block types include: 
    'Text Block': with timer, title, and description
    'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'Branching Block'(includes two types, choose one of the two): 
    'Simple Branching' with Title, Timer, Proceed To Branch List  
    'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
    'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
    “You are good at this…”. “You can't do this because...”. Then also give:
    FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    
    'Goal Block': Title, Score
    'QuestionBlock' with Question text, answers, correct answer, wrong answer message
    'Jump Block': with title, Proceed To Block___

    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    Gamified Scenario: A type of Exit Game scenario structure in which multiple or single TextBlocks, MediaBlocks will be used to give clues of information to students. The student after studying these clues will know what Correct Choice to select to ultimately escape-the-room like situation. The choices are given via Branching Blocks (Simple or Conditional). These blocks give users only 2 choices. 1 is Incorrect or Partially-Correct Choice. The other 2nd one is the Correct Choice.
    The Incorrect Choice leads to Incorrect Branch having 'FeedbackAndFeedforwardBlock' and 'Jump Block'. This 'Jump Block' routes the student back to the Branching Block which offered this Incorrect Choice so user can select the Correct Choice to move forward.
    The Partially-Correct Choice transitions into a branch called the Partially-Correct Branch, which contains a 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' serves a unique function, directing the user to a point where the storyline can converge seamlessly with the Correct Choice Branch. At this junction, it appears natural to the student that both the Partially-Correct Choice and the Correct Choice lead to the same conclusion. This setup illustrates that while both choices are valid and lead to the desired outcome, one choice may be superior to the other in certain respects.
    The Correct Choice leads to Correct Branch that has single or multiple number of 'Text Blocks', 'Media Blocks', 'Question Blocks', 'FeedbackAndFeedforwardBlock' and a 'Branching Block' (Simple or Conditional). This Branch progresses the actual story by using the Text and Media Blocks to provide clues of information that help student to select subsequent Correct Choice in the Branching Block and leading the student with each Correct Choice to ultimately escape the room situation and being greeted with a good 'Goal Block' score.
    ***
    ***YOU WILL BE REWARD IF:
    All the TextBlocks in the branches, has valid detailed information in the form of clues of the subject matters such that you are teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
    TextBlocks should provide extremely specific and detailed information so user can get as much knowledge and facts as there is available.
    The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
    user interest is kept. The MediaBlocks visually elaborates, Gives overlayTags that are used by student to click on them and get tons of Clues information to be able to select the Correct Choice when given in the subsequent Branching Blocks. 
    The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
    Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
    so the user uses critical thinking skills and is encouraged to think about how much of the Learning Objectives has been achieved.
    ***
    ***YOU WILL BE PENALISED IF:
    The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
    The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
    ***
    The Example below is just for your concept and do not absolutely produce the same example in your Exit Game.
    Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
    You are creative in the manner of choosing the number of TextBlocks, MediaBlocks and QuestionBlocks to give best quality information to students. You are free to choose TextBlocks or MediaBlocks or QuestionBlocks or both or multiple of them to convey best quality, elaborative information.
    Make sure students learn from these TextBlocks and MediaBlocks, and are tested via QuestionBlocks.
    You are creatively free to choose the placements of Branching Blocks (Simple or Conditional) and you should know that it is mandatory for you to give only 2 Choices, Incorrect or Partially-Correct choice (You Decide) and the Correct Choice (Mandatory).
    Note that the Incorrect Choice leads to 'FeedbackAndFeedforwardBlock' and 'Jump Block', which will lead the student to the Branching Block that offered this Incorrect Choice.
    The Partially-Correct Choice leads to the branch with 'Goal Block', 'FeedbackAndFeedforwardBlock', and a 'Jump Block'. This 'Jump Block' leads to one of the blocks in the Correct Choice branch, seemlessly transitioning story since the Partially-Correct and Correct Choice both has same conclusion but the student gets different Goal Block scores. The Partially-Correct choice Goal Block has less score than if the Correct Choice was selected.
    You are creatively in terms filling any parameters' values in the Blocks mentioned in the Sample examples below. The Blocks has static parameter names in the left side of the ':'. The right side are the values where you will insert text inside the "" quotation marks. You are free to fill them in the way that is fitting to the Exit Game gamified scenario you are creating. 
    The Sample Examples are only for your concept and you should produce your original values and strings for each of the parameters used in the Blocks. 
    
    \nOverview structure of the Exit Game\n
    ScenarioType
    LearningObjectives
    ContentAreas
    Start
    TextBlock (Welcome to the Exit Game)
    TextBlock/s (Information elaborated/ subject matter described in detail)
    MediaBlock/s (To give illustrated, complimentary material to elaborate on the information given in Text Blocks. To give such information, that needs illustrated explaination.)
    QuestionBlock/s
    FeedbackAndFeedforwardBlock
    SelfAssessmentTextBlock
    TestBlocks => QuestionBlock/s, GoalBlock
    \nEnd of Overview structure\n

    \n\nSAMPLE EXAMPLE\n\n
{{
    "ScenarioType": "Gamified Scenario",
    "LearningObjectives": [
        "This mandatory block is where you !Give users single or multiple learning objectives of the Exit Game!"
    ],
    "ContentAreas": [
        "This mandatory block is where you !Give users Content Areas of the Exit Game single or multiple!"
    ],
    "Start": "A Exit Game name here",
    "Blocks": [
        {{
            "id": "1",
            "Purpose": "This block (can be used single or multiple times or None depends on the content to be covered in this gamified senario) is where you !Begin by giving welcome message to the Exit Game. In further Text Blocks down this scenario in Branches, you use these blocks to give detailed information on every aspect of various subject matters belonging to each branch. The TextBlocks in branches are used either Single or Multiple Times and are bearers of detailed information and explanations that helps the final Exit Game to be produced having an extremely detailed information in it.",
            "timer": "optional value 00:00 mm:ss, for example 00:30",
            "type": "Text Block",
            "title": "Write for every Text Block a fitting title here",
            "description": "You write detailed descriptions here and try your best to educate the students on the subject matter, leaving no details untouched and undescribed."
        }},
        {{
            "id": "2",
            "Purpose": "This block (can be used single or multiple times or None  depends on the content to be covered in the Text Blocks relevant to this Media Block) is where you !Give students an illustrative experience that elaborates on the information given in Text Blocks and are used in a complimentary way to them. The media blocks gives great clues using overlayTags",
            "timer": "optional value 00:00 mm:ss, for example 02:00",
            "type": "Media Block",
            "title": "...",
            "mediaType": "360-image/Image (Preferred)/Video etc",
            "description": "...",
            "overlayTags": [
                {{
                    "textTag/imageTag/videoTag": "Explain and teach the students, using these overlayTags, the different aspects of the information for this media block. Also give instructions here of how to shoot these medias, what information are they elaborating based on the information present in Text Blocks. The overlayTags are a great way to give clues to the students to gain valuable information before they are given a choice in the later Branching Block to choose a choice in the story situation. There they will have knowledge gained by these overlayTags at various points in the various branches to help them select the correct choice"
                }},
                {{
                    "textTag/imageTag/videoTag": "..."
                }}
            ]
        }},
        {{
            "id": "3",
            "Purpose": "This block is where you !Divide the Exit Game content into ONLY TWO choices, that users can select and the corresponding divided branches leads to a consequence of the choice selected.!",
            "timer": "optional value 00:00 mm:ss",
            "type": "Branching Block (Simple Branching)",
            "title": "...",
            "branches": {{
                "3.1": "text (Partially-Correct Choice or Incorrect Choice)",
                "3.2": "text (Correct Choice)",
        }},
        {{
            "id": "3.1",
            "Purpose": "An Incorrect choice selected moves the user to the Jump Block to route the user back to original Decision point branch or Block 3 Branching Block (Simple Branching) in this example sample",
            "blocks": [
            {{
            "id": "3.1.1",
            "Purpose": "Mandatory for every branch. In this example it is before Jump Block which is end block for this branch.",
            "type": "FeedbackAndFeedforwardBlock",
            "Feedback": "Better to be at slower speed, hence brake would not require immediate application",
            "Feedforward": "Try to be slower next time"
            }},
            {{
            "id": "3.1.2",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3"
            }}
        ]}},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Text Block",
                    "title": "...",
                    "description": "..."
                }},
                {{
                    "id": "3.2.2",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Media Block",
                    "title": "Waiting at intersection after red light stop",
                    "mediaType": "Image",
                    "description": "An image of cars standing at the red light, waiting and preferably turning off the engines while wait is about a minute long. Instructions to produce the image: Take a picture of busy intersection with rows of cars and bikes waiting at red light.",
                    "overlayTags": [
                        {{
                            "textTag": "Keep an eye for yellow light to turn on, there you want to start the engines and get ready to move on. "
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "Purpose": "Mandatory for every branch. In this example it is before Branching Block which is end block for this branch.",
                    "type": "FeedbackAndFeedforwardBlock",
                    "Feedback": "...",
                    "Feedforward": ""
                }},
                {{
                    "id": "3.2.4",
                    "Purpose": "This block is where you !Divide the Exit Game content into ONLY TWO choices, whilst asking a question at the same time. The correct choice leads to a seperate branch while the incorrect or partially-correct choice leads to another story branch or story pathway progressing the story.",   
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "...",
                    "questionText": "...",
                    "proceedToBranchForEachAnswer": [
                        {{
                            "text": "... (Partially-Correct Choice or Incorrect Choice)",
                            "proceedToBlock": "3.2.4.1"
                        }},
                        {{
                            "text": "... (Correct Choice)",
                            "proceedToBlock": "3.2.4.2"
                        }}
                    ]
                }}
            ]
        }},
        {{
            "id": "3.2.4.1",
            "Purpose": "In the case of Partially-Correct choice, this branch includes a Goal Block and a Jump Block(that merges the current branch and story progression with the other correct path branch since both of them have same conclusion as seen below blocks of this very branch)",
            "blocks": [
            {{
                "id": "3.2.4.1.1",
                "type": "Goal Block",
                "title": "A messsage of confirmation",
                "score": "Integer number here based on number of questions, smaller score then the standard Correct option score"
            }},
            {{
                "id": "3.2.4.1.2",
                "Purpose": "Mandatory for every branch. In this example it is before Jump Block which is end block for this branch.",
                "type": "FeedbackAndFeedforwardBlock",
                "Feedback": "...",
                "Feedforward": "..."
            }},
            {{
                "id": "3.2.4.1.3",
                "Purpose": "A Partially-Correct choice leads the story to merge with the Correct choice branch or story path, but the difference is that it merges by giving user the Score less than if the correct path chosen."
                "type": "Jump Block",
                "title": "...",
                "proceedToBlock": "3.2.4.2.2"
            }}
            ]
        }},
        {{
            "id": "3.2.4.2",
            "blocks": [
                {{
                    "id": "3.2.4.2.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Text Block",
                    "title": "...",
                    "description": "..."
                }},
                {{
                    "id": "3.2.4.2.2",
                    "Purpose": "This Question Block (Single or Multiple QuestionBlocks) is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the Exit Game's content and importance at hand",
                    "type": "Question Block",
                    "questionText": "...",
                    "answers": [
                        "...",
                        "...",
                        "...",
                        "..."
                    ],
                    "correctAnswer": "...",
                    "wrongAnswerMessage": "..."
                }},
                {{
                    "id": "3.2.4.2.3",
                    "Purpose": "Mandatory for every branch. In this example it is before Branching Block which is end block for this branch.",
                    "type": "FeedbackAndFeedforwardBlock",
                    "Feedback": "...",
                    "Feedforward": "..."
                }},
                {{
                    "id": "3.2.4.2.4",
                    "Purpose": "This block is where you !Divide the Exit Game content into ONLY TWO choices, that users can select and the corresponding divided branches leads to a consequence of the choice selected.!",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Branching Block (Simple Branching)",
                    "title": "...",
                    "branches": {{
                        "3.2.4.2.4.1": "text (Partially-Correct Choice or Incorrect Choice)",
                        "3.2.4.2.4.2": "text (Correct Choice)",
                }},
                {{
                    "id": "3.2.4.2.4.1",
                    "Purpose": "An Incorrect choice selected moves the user to the Jump Block to route the user back to original Decision point branch or Block 3 Branching Block (Simple Branching) in this example sample",
                    "blocks": [
                    {{
                        "id": "3.2.4.2.4.1.1",
                        "Purpose": "Mandatory for every branch. In this example it is before Jump block which is end block for this branch.",
                        "type": "FeedbackAndFeedforwardBlock",
                        "Feedback": "...",
                        "Feedforward": "..."
                    }},
                    {{
                    "id": "3.2.4.2.4.1.2",
                    "type": "Jump Block",
                    "title": "Reevaluate Your Choices",
                    "proceedToBlock": "3.2.4"
                }}]}},
                {{
                "id": "3.2.4.2.4.2",
                "blocks": [
                {{
                    "id": "3.2.4.2.4.2.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Text Block",
                    "title": "...",
                    "description": "..."
                }},
                {{
                    "id": "3.2.4.2.4.2.2",
                    "Purpose": "Mandatory for every branch. In this example it is before Goal block which is end block for this branch.",
                    "type": "FeedbackAndFeedforwardBlock",
                    "Feedback": "...",
                    "Feedforward": "..."
                }},
                {{
                    "id": "3.2.4.2.4.2.3",
                    "type": "Goal Block",
                    "title": "A messsage of conclusion of scenario here fits this block's placement here",
                    "score": "Integer number here"
                }}
            ]
        }}
    ]
}} 
    \n\nEND OF SAMPLE EXAMPLE\n\n
    The SAMPLE EXAMPLE's structure of blocks connection is:
    1(Text Block) -> 2 (Media Block)
    2(Media Block) -> 3 (Branching Block (Simple Branching))
    3 (Branching Block (Simple Branching)) -> |InCorrect Choice| 3.1 
    3 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2
    3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock) 
    3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
    3.1.2 (Jump Block) -> 3 (Branching Block (Simple Branching))
    3.2 -> 3.2.1 (Text Block)
    3.2.1 (Text Block) -> 3.2.2 (Media Block)
    3.2.2 (Media Block) -> 3.2.3 (FeedbackAndFeedforwardBlock)
    3.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4 (Branching Block (Conditional Branching))
    3.2.4 (Branching Block (Conditional Branching)) -> |Partially-Correct Choice| 3.2.4.1
    3.2.4 (Branching Block (Conditional Branching)) -> |Correct Choice| 3.2.4.2
    3.2.4.1 -> 3.2.4.1.1 (Goal Block)
    3.2.4.1.1 (Goal Block) -> 3.2.4.1.2 (FeedbackAndFeedforwardBlock)
    3.2.4.1.2 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.1.3
    3.2.4.1.3 (Jump Block) -> 3.2.4.2.2 (Question Block)
    3.2.4.2 -> 3.2.4.2.1 (Text Block)
    3.2.4.2.1 (Text Block) -> 3.2.4.2.2 (Question Block)
    3.2.4.2.2 (Question Block) -> 3.2.4.2.3 (FeedbackAndFeedforwardBlock)
    3.2.4.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4 (Branching Block (Simple Branching))
    3.2.4.2.4 (Branching Block (Simple Branching)) -> |Incorrect Choice| 3.2.4.2.4.1
    3.2.4.2.4 (Branching Block (Simple Branching)) -> |Correct Choice| 3.2.4.2.4.2
    3.2.4.2.4.1 -> 3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock)
    3.2.4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.4.2.4.1.2
    3.2.4.2.4.1.2 (Jump Block) -> 3.2.4 (Branching Block (Conditional Branching))
    3.2.4.2.4.2 -> 3.2.4.2.4.2.1 (Text Block)
    3.2.4.2.4.2.1 (Text Block) -> 3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock)
    3.2.4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 3.2.4.2.4.2.3 (Goal Block)

    ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
    1 (Text Block) -> 2 (Text Block)
    2 (Text Block) -> 3 (Media Block)
    3 (Media Block) -> 4 (Branching Block (Simple Branching))
    4 (Branching Block (Simple Branching)) -> |Partially-Correct choice| 4.1 
    4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2
    4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
    4.1.1 (FeedbackAndFeedforwardBlock) -> 4.1.2 (Goal Block)
    4.1.2 (Goal Block) -> |Jump Block| 4.1.2 
    4.1.2 (Jump Block) -> 4.2.3 (Branching Block (Simple Branching))
    4.2 -> 4.2.1 (Media Block)
    4.2.1 (Media Block) -> 4.2.2 (Question Block)
    4.2.2 (Question Block) -> 4.2.3 (FeedbackAndFeedforwardBlock)
    4.2.3 (FeedbackAndFeedforwardBlock) -> 4.2.4 (Branching Block (Simple Branching))
    4.2.4 (Branching Block (Simple Branching)) -> |Incorrect choice| 4.2.4.1
    4.2.4 (Branching Block (Simple Branching)) -> |Correct choice| 4.2.4.2
    4.2.4.1 -> 4.2.4.1.1 (FeedbackAndFeedforwardBlock) 
    4.2.4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.2.4.1.2
    4.2.4.1.2 (Jump Block) -> 4.2.4 (Branching Block (Simple Branching))
    4.2.4.2 -> 4.2.4.2.1 (Media Block)
    4.2.4.2.1 (Media Block) -> 4.2.4.2.2 (FeedbackAndFeedforwardBlock) 
    4.2.4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.4.2.3 (Goal Block)

    AND ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
    1 (Text Block) -> 2 (Text Block)
    2 (Text Block) -> 3 (Media Block)
    3 (Media Block) -> 4 (Branching Block (Conditional Branching))
    4 (Branching Block (Conditional Branching)) -> |Incorrect choice| 4.1 
    4 (Branching Block (Conditional Branching)) -> |Correct choice| 4.2
    4.1 -> 4.1.1 (FeedbackAndFeedforwardBlock)
    4.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 4.1.2
    4.1.2 (Jump Block) -> 4 (Branching Block (Conditional Branching))
    4.2 -> 4.2.1 (Text Block)
    4.2.1 (Text Block) -> 4.2.2 (FeedbackAndFeedforwardBlock)
    4.2.2 (FeedbackAndFeedforwardBlock) -> 4.2.3 (Goal Block)

    AND AN ANOTHER SAMPLE EXAMPLE STRUCTURE IS:
    1 (Text Block) -> 2 (Text Block)
    2 (Text Block) -> 3 (Branching Block (Conditional Branching))
    3 (Branching Block (Conditional Branching)) -> |Incorrect choice| 3.1 
    3 (Branching Block (Conditional Branching)) -> |Correct choice| 3.2
    3.1 -> 3.1.1 (FeedbackAndFeedforwardBlock)
    3.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.1.2
    3.1.2 (Jump Block) -> 3 (Branching Block (Conditional Branching))
    3.2 -> 3.2.1 (Text Block)
    3.2.1 (Text Block) -> 3.2.2 (Media Block)
    3.2.2 (Media Block) -> 3.2.3 (Question Block)
    3.2.3 (Question Block) -> 3.2.4 (Question Block)
    3.2.4 (Question Block) -> 3.2.5 (Question Block)
    3.2.5 (Question Block) -> 3.2.6 (FeedbackAndFeedforwardBlock)
    3.2.6 (FeedbackAndFeedforwardBlock) -> 3.2.7 (Branching Block (Simple Branching))
    3.2.7 (Branching Block (Simple Branching)) -> |Incorrect choice| 3.2.7.1
    3.2.7 (Branching Block (Simple Branching)) -> |Correct choice| 3.2.7.2
    3.2.7.1 -> 3.2.7.1.1 (FeedbackAndFeedforwardBlock)
    3.2.7.1.1 (FeedbackAndFeedforwardBlock) -> |Jump Block| 3.2.7.1.2
    3.2.7.1.2 (Jump Block) -> 3.2.7 (Branching Block (Simple Branching))
    3.2.7.2 ->  3.2.7.2.1 (Text Block)
    3.2.7.2.1 (Text Block) -> 3.2.7.2.2 (Text Block)
    3.2.7.2.2 (Text Block) -> 3.2.7.2.3 (FeedbackAndFeedforwardBlock)
    3.2.7.2.3 (FeedbackAndFeedforwardBlock) -> 3.2.7.2.4 (Goal Block)
    
    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.  
    Give concise, relevant, clear, and descriptive instructions as you are an Exit Game creator that has expertise 
    in molding asked information into the Gamified scenario structure.

    !!IMPORTANT NOTE REGARDING CREATIVITY: Know that you are creative to use as many or as little
    Text Blocks, Media Blocks, Question Blocks, Branching Blocks as you deem reasonable and fitting to the
    content and aim of the subject scenario.

    NEGATIVE PROMPT: Do not respond outside the JSON format.     
    
    Chatbot:"""
)


prompt_branched_setup = PromptTemplate(
    input_variables=["input_documents","human_input","content_areas","learning_obj"],
    template="""
    You are an educational bot which is designed to take the inputs of Parameters and using the information
    and context of these parameters, you create subtopics from the main subject of interest set by these parameters.
    For each of the subtopic that contributes to the main subject, you create a detailed information-database of every possible information available
    using the Parameters.
    Input Paramters:
    'Human Input': {human_input};
    'Input Documents': {input_documents};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};

    Sample Format:
    Main Topic Name
    Subtopic 1 Name: Extremely Detailed Explanation and information...
    Subtopic 2 Name: Extremely Detailed Explanation and information...
    Subtopic 3 Name: Extremely Detailed Explanation and information...
    and so on Subtopics that you creatively deem necessary to include...

    Chatbot (Tone of a teacher teaching student in great detail):"""
)

prompt_branched = PromptTemplate(
    input_variables=["response_of_bot","human_input","content_areas","learning_obj"],
    template="""
    You are an educational bot creator that creates engaging educational and informative content in a Micro Learning Format using
    a system of blocks. You give explanations and provide detailed information such that you are teaching a student.
    !!!WARNING!!!
    Explain the material itself, Please provide detailed, informative explanations that align closely with the learning objectives and content areas provided. Each response should not just direct the learner but educate them by elaborating on the historical, technical, or practical details mentioned in the 'Input Documents'. Use simple and engaging language to enhance understanding and retention. Ensure that each explanation directly supports the learners' ability to meet the learning objectives by providing comprehensive insights into the topics discussed.
    !!!WARNING END!!!

    ***WHAT TO DO***
    To accomplish Micro Learning Scenario creation, YOU will:

    1. Take the "Human Input" which represents the subject content topic or description for which the Micro Learning Scenario is to be formulated.
    2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
    and create the Micro Learning Scenario according to these very "Learning Objectives" and "Content Areas" specified.
    3. Generate a JSON-formatted structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the Micro Learning Scenario content efficiently and logically.
    
    'Human Input': {human_input};
    'Input Documents': {response_of_bot};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};
    ***WHAT TO DO END***

    
    The Micro Learning Scenario are built using blocks, each having its own parameters.
    Block types include: 
    'TextBlock' with timer(optional), title, and description
    'MediaBlock' with timer(optional), title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Mandatory Overlay tags used as hotspots on the Media as text, video or audio
    'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
    “You are good at this…”. “You can't do this because...”. Then also give:
    FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    'TestBlocks' contains QuestionBlock/s
    'QuestionBlock' with Question text, answers, correct answer, wrong answer message
    'SimpleBranchingBlock' with timer(optional), Title, ProceedToBranchList  
    'JumpBlock' with title, ProceedToBlock
    'GoalBlock' with Title, Score

    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    Micro Learning Scenario: A type of educational, information providing and testing structure in which multiple or single TextBlocks, MediaBlocks and QuestionBlocks will be 
    used to give detailed explanations to users based on "Learning Objectives", "Content Areas" and "Input Documents". The SimpleBranchingBlock is used to divide the Micro Learning Scenario into subtopics. Each subtopic having its own multiple or single TextBlocks, MediaBlocks and QuestionBlocks to train user. At the end of each branch, there will be FeedbackAndFeedforwardBlock and after it a TestBlocks Array is used that encompasses a single or series of QuestionBlock/s to test user knowledge of the Branch, followed by the JumpBlock at the very end to move the user to the SimpleBranchingBlock for being able to begin and access another branch to learn.
    ***
    ***YOU WILL BE REWARD IF:
    All the TextBlocks in the branches, has valid step-by-step and detailed information of the subject matters such that you are teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
    TextBlocks should provide extremely specific and detailed information so user can get as much knowledge and facts as there is available.
    The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
    user interest is kept. 
    The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
    Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
    so the user uses critical thinking skills and is encouraged to think about how much of the Learning Objectives has been achieved.
    ***
    ***YOU WILL BE PENALISED IF:
    The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
    The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
    ***
    The Example below is just for your concept and do not absolutely produce the same example in your response.
    The Example below is just for your concept and the number of TextBlocks, MediaBlocks, QuestionBlocks, Branches etc Differ with the amount of subject content needed to be covered in 'Input Documents'.
    Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
    You are creative in the manner of choosing the number of TextBlocks and MediaBlocks to give best quality information to students. In each branch you are free to choose TextBlocks or MediaBlocks or both or multiple of them to convey best quality, elaborative information.
    Make sure students learn from these TextBlocks and MediaBlocks.

    \nOverview structure of the Micro Learning Scenario\n
    ScenarioType
    LearningObjectives
    ContentAreas
    Start
    TextBlock (Welcome message to the Micro Learning Scenario and proceedings)
    MediaBlock (To give visualized option to select learning path with pertinent overlayTags if any)
    SimpleBranchingBlock (To select from a learning subtopic (Branches). The number of Branches equal to the number of Learning Objectives, each branch covering a Learning Objective)
    Branch 1,2,3... => each branch having with its own LearningObjective,TextBlock/s(Explains the content) or None,MediaBlock/s or None (Illustratively elaborate the TextBlock's content),QuestionBlock/s or None,FeedbackAndFeedforwardBlock,TestBlocks Array encompassing a single or series of QuestionBlock/s,JumpBlock
    \nEnd of Overview structure\n

    \nSAMPLE EXAMPLE START: MICRO LEARNING SCENARIO:\n
{{
    "ScenarioType": "Branched Scenario",
    "LearningObjectives": [
        "This mandatory block is where you !Give users single or multiple learning objectives of the scenario!"
    ],
    "ContentAreas": [
        "This mandatory block is where you !Give users Content Areas of the scenario single or multiple!"
    ],
    "Start": "A Micro Learning Scenario name here",
    "Blocks": [
        {{
            "id": "1",
            "Purpose": "This block (can be used single or multiple times or None depends on the content to be covered in the scenario) is where you !Begin by giving welcome message to the user. In further Text Blocks down the structure in Branches, you use these blocks to give detailed information on every aspect of various subject matters belonging to each branch. The TextBlocks in branches are used either Single or Multiple Times and are bearers of detailed information and explanations that helps the final Micro Learning Scenario to be produced having an extremely detailed information in it.",
            "type": "Text Block",
            "title": "",
            "description": "You write detailed descriptions here and try your best to educate the students on the subject matter, leaving no details untouched and undescribed."
        }},
        {{
            "id": "2",
            "Purpose": "This block (can be used single or multiple times or None  depends on the content to be covered in the Text Blocks relevant to this Media Block) is where you !Give students an illustrative experience that elaborates on the information given in Text Blocks and are used in a complimentary way to them.",
            "type": "Media Block",
            "title": "",
            "mediaType": "360-image/Image (Preferred)/Video etc",
            "description": "",
            "overlayTags": [
                {{
                    "textTag/imageTag/videoTag": "Explain and teach the students, using these overlayTags, the different aspects of the information for this media block. Also give instructions here of how to shoot these medias, what information are they elaborating based on the information present in Text Blocks."
                }},
                {{
                    "textTag/imageTag/videoTag": ""
                }}
            ]
        }},
        {{
            "id": "3",
            "Purpose": "This mandatory block is where you !Divide the Micro learning scenario content into subtopics that users can select and access the whole information of those subtopics in the corresponding divided branches!",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Renewable Energy Path",
            "branches": {{
                "3.1": "A Micro learning subtopic based on each Learning Objective",
                "3.2": "A Micro learning subtopic based on each Learning Objective",
                "3.3": "and so on..."
            }},
            "blocks": [
                {{
                    "id": "3.1",
                    "blocks": [
                        {{
                            "id": "3.1.1",
                            "LearningObjective": [
                                "This mandatory block is where you !Write the Learning objective for this specific branch!"
                            ]
                        }},
                        {{
                            "id": "3.1.2",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.1.3",
                            "type": "Media Block",
                            "title": "",
                            "mediaType": "360-image/Image (Preferred)/Video etc",
                            "description": "",
                            "overlayTags": [
                                {{
                                    "textTag/imageTag/videoTag": ""
                                }},
                                {{
                                    "textTag/imageTag/videoTag": ""
                                }}
                            ]
                        }},
                        {{
                            "id": "3.1.4",
                            "Purpose": "This OPTIONAL block is where you !Test the student's knowledge of the specific Text or Media Blocks information it comes after, in regards to their information content. The QuestionBlocks can be single or multiple depending on the subject content and importance at hand",
                            "type": "Question Block",
                            "questionText": "",
                            "answers": [
                                "",
                                "",
                                "",
                                ""
                            ],
                            "correctAnswer": "",
                            "wrongAnswerMessage": ""
                        }},
                        {{
                            "id": "3.1.5",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.1.6",
                            "TestBlocks": [
                                {{
                                    "id": "3.1.6.1",
                                    "Purpose": "This Question Block's status in the 'Test' array here is MANDATORY(Single or Multiple QuestionBlocks) now. This is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the subject content and importance at hand.",
                                    "type": "Question Block",
                                    "questionText": "",
                                    "answers": [
                                        "",
                                        "",
                                        "",
                                        ""
                                    ],
                                    "correctAnswer": "",
                                    "wrongAnswerMessage": ""
                                }}
                            ]
                        }},
                        {{
                            "id": "3.1.7",
                            "Purpose": "Mandatory",
                            "type": "JumpBlock",
                            "title": "Return to Topic Selection",
                            "proceedToBlock": "3"
                        }}
                    ]
                }},
                {{
                    "id": "3.2",
                    "blocks": [
                        {{
                            "id": "3.2.1",
                            "LearningObjective": [
                                "This mandatory block is where you !Write the Learning objective for this specific branch!"
                            ]
                        }},
                        {{
                            "id": "3.1.2",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.5",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.2.6",
                            "TestBlocks": [
                                {{
                                    "id": "3.2.6.1",
                                    "Purpose": "This Question Block's status in the 'Test' array here is MANDATORY(Single or Multiple QuestionBlocks) now. This is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the subject content and importance at hand.",
                                    "type": "Question Block",
                                    "questionText": "",
                                    "answers": [
                                        "",
                                        "",
                                        "",
                                        ""
                                    ],
                                    "correctAnswer": "",
                                    "wrongAnswerMessage": ""
                                }},
                                {{
                                    "id": "3.2.6.2",
                                    "Purpose": "This Question Block's status in the 'Test' array here is MANDATORY(Single or Multiple QuestionBlocks) now. This is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the subject content and importance at hand.",
                                    "type": "Question Block",
                                    "questionText": "",
                                    "answers": [
                                        "",
                                        "",
                                        "",
                                        ""
                                    ],
                                    "correctAnswer": "",
                                    "wrongAnswerMessage": ""
                                }}
                            ]
                        }},
                        {{
                            "id": "3.2.7",
                            "Purpose": "Mandatory",
                            "type": "JumpBlock",
                            "title": "Return to Topic Selection",
                            "proceedToBlock": "3"
                        }}
                    ]
                }},
                {{
                    "id": "3.3 and so on branches depending upon learning objectives",
                    "blocks": [
                        {{
                            "id": "3.3.1",
                            "LearningObjective": [
                                "This mandatory block is where you !Write the Learning objective for this specific branch!"
                            ]
                        }},
                        {{
                            "id": "3.3.2",
                            "type": "Media Block",
                            "title": "",
                            "mediaType": "360-image/Image (Preferred)/Video etc",
                            "description": "",
                            "overlayTags": [
                                {{
                                    "textTag/imageTag/videoTag": ""
                                }},
                                {{
                                    "textTag/imageTag/videoTag": ""
                                }}
                            ]
                        }},
                        {{
                            "id": "3.3.3",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.3.4",
                            "TestBlocks": [
                                {{
                                    "id": "3.3.4.1",
                                    "Purpose": "This Question Block's status in the 'Test' array here is MANDATORY(Single or Multiple QuestionBlocks) now. This is where you !Test the student's knowledge of this specific branch in regards to its information given in its TextBlocks and MediBlocks. The QuestionBlocks can be single or multiple depending on the subject content and importance at hand.",
                                    "type": "Question Block",
                                    "questionText": "",
                                    "answers": [
                                        "",
                                        "",
                                        "",
                                        ""
                                    ],
                                    "correctAnswer": "",
                                    "wrongAnswerMessage": ""
                                }}
                            ]
                        }},
                        {{
                            "id": "3.3.5",
                            "Purpose": "Mandatory",
                            "type": "JumpBlock",
                            "title": "Return to Topic Selection",
                            "proceedToBlock": "3"
                        }}
                    ]
                }}
            ]
        }}
    ]
}}
    \n\nEND OF SAMPLE EXAMPLE\n\n

    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable. 
    Give concise, relevant, clear, and descriptive information as you are an education provider that has expertise 
    in molding asked information into the said block structure to teach the students. 

    NEGATIVE PROMPT: Do not respond outside the JSON format.   

    !!!WARNING!!!
    Explain the material itself, Please provide detailed, informative explanations that align closely with the learning objectives and content areas provided. Each response should not just direct the learner but educate them by elaborating on the historical, technical, or practical details mentioned in the 'Input Documents'. Use simple and engaging language to enhance understanding and retention. Ensure that each explanation directly supports the learners' ability to meet the learning objectives by providing comprehensive insights into the topics discussed.
    !!!WARNING END!!!

    Chatbot (Tone of a teacher teaching student in great detail):"""
)


prompt_simulation_pedagogy_setup = PromptTemplate(
    input_variables=["input_documents","human_input","content_areas","learning_obj"],
    template="""
    You are an educational bot which is designed to take the inputs of Parameters and using the information
    and context of these parameters, you create progressive simulation story where the student goes
    through a simulation story and is given choices. For each choices, a consequence is given if it was
    taken by the student. The consequence can lead to further choices, ultimately to the end of the story.
    Henceforth, this kind of story will have multiple endings based on user choices. Some choices can even merge 
    with the same conclusion at the end or at the intermediate stages of the story.
    Input Paramters:
    'Human Input': {human_input};
    'Input Documents': {input_documents};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};

    !CAUTION!:
    You should give a complete response with the complete story, writing all the possible challenges, 
    the choices needed to overcome them or that can lead to failure, and the consequences of all those choices.
    This is because, your response is NOT used in a conversational way, this means student will NOT be interacting
    with you directly. Once your response is generated, it will be fed to another system that will translate it to 
    a frontend Flowchart and Decision tree like visualizations. So keep your response as complete as possible.

    AVOID using numbers to list choices or consequences. Use ONLY words like: 'if you decided to do this, then this happens,...'
    
    Chatbot (Tone of a teacher instructing and teaching student in great detail):"""
)

prompt_simulation_pedagogy = PromptTemplate(
    input_variables=["response_of_bot","human_input","content_areas","learning_obj"],
    template="""
    You are an educational bot creator that creates engaging Simulation Scenarios in a Simulation Format using
    a system of blocks. You give step-by-step instructions and provide detail information such that 
    you are instructing and teaching a student.

    ***WHAT TO DO***
    To accomplish Simulation Scenarios creation, YOU will:

    1. Take the "Human Input" which represents the content topic or description for which the scenario is to be formulated.
    2. According to the "Learning Objectives" and "Content Areas", you will utilize the meta-information in the "Input Documents" 
    and create the scenario according to these very "Learning Objectives" and "Content Areas" specified.
    You Prefer to make simulation such that a choice may lead to a consequnece that may lead to more choice or choices that may lead to more consequences, evetually reaching the end of the scenario.
    3. Generate a JSON-formatted structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the content efficiently and logically.
    
    'Human Input': {human_input};
    'Input Documents': {response_of_bot};
    'Learning Objectives': {learning_obj};
    'Content Areas': {content_areas};
    ***WHAT TO DO END***

    
    The Simulation Scenario are built using blocks, each having its own parameters.
    Block types include: 
    'TextBlock' with timer(optional), title, and description
    'MediaBlock' with timer(optional), title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'FeedbackAndFeedforwardBlock' with title, and description(FEEDBACK: Is Evaluative or corrective information about a person's performance of a task, action, event, or process,  etc. which is used as a basis for improvement. 
    “You are good at this…”. “You can't do this because...”. Then also give:
    FEEDFORWARD: Describes the problem and its influences and leads towards solutions. Proactive guidance and suggestions for improvement, aiming to enhance future performance and foster continuous learning. Helps the student to create a well-defined plan on how to improve. “Would you practice this…” “Maybe you could add…” )
    'Debriefing' with descritpion(Debrief the situation and results of the branch such that students can Reflect on their performance, Analyze the decisions, Identify and discuss discrepancies, Reinforce correct behavior, Learn from mistakes, Promote a deeper understanding) 
    'Reflection' with descritpion(Use Reflection to allows students to be able to have Personal Understanding, Identifying Strengths and Weaknesses, Insight Generation of the choices and path or branch they took)
    'Branching Block (Simple Branching)' with timer(optional), Title, ProceedToBranchList
    'Branching Block (Conditional Branching)' with timer(optional),Title, questionText, answers, proceedToBranchForEachAnswer
    'JumpBlock' with title, ProceedToBlock
    'GoalBlock' with Title, Score

    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    Simulation Pedagogy Scenario: A type of structure which takes the student on a simulated story where 
    the student is given choices based on which they face consequences. The simulation is based on the information in 
    "Learning Objectives", "Content Areas" and "Input Documents". The 'Branching Block (Simple Branching)'/'Branching Block (Conditional Branching)'  
    is used to divide the choices for the student to take. Then, for selected choices, branches the Simulation Scneario into 
    consequence branches. Each consequence branch can have its own branches that can divide further 
    to have their own branches, untill the simulation story ends covering all aspects of the information
    for scenario creation. The start of the scenario has Briefing. The end of each of that branch that ends the simulation story and
    give score via a Goal Block, this type of branch has FeedbackAndFeedforwardBlock, Debriefing and Reflection blocks. 
    There are two types branches. The DIVISIBLE type branch divides further via a 'Branching Block (Simple Branching)'/'Branching Block (Conditional Branching)' and this 
    branch type has NO Goal Block, FeedbackAndFeedforwardBlock, Debriefing and Reflection blocks. The DIVISIBLE branch type gives rise to
    more Branches that may be further DIVISIBLE or NON-DIVISIBLE type branches. The NON-DIVISIBLE type branches are the branches where
    a simulation path ends and the story of that path is finished. The NON-DIVISIBLE type branch has at the end Goal Block, FeedbackAndFeedforwardBlock, Debriefing and Reflection blocks.
    Furthermore, a NON-DIVISIBLE-MERGE branch includes in addition to TextBlocks and MediaBlocks, the MANDATORY FeedbackAndFeedforwardBlock and JumpBlock (Used in situation where the story of a 
    branch leads to another branch hence we use JumpBlock to connect the progressive story because story paths 
    can merge as well to have the 1 same conclusion). Use NON-DIVISIBLE-MERGE only in the situation where
    a story of the branch leads to and connects to the progressive story of another branch such that both the choices
    leads to the same conclusion for that part of the story.
    ***

    ***YOU WILL BE REWARD IF:
    You Prefer to make simulation such that a choice may lead to a consequnece that may lead to more choice or choices that may lead to more consequences, evetually reaching the end of the scenario.
    All the TextBlocks in the branches, has valid step-by-step and detailed instructions of the subject matters such that you are instructing and teaching a student. The TextBlocks are used to give complete information of a subject matter available to you and is there so that the user actually learns from. 
    TextBlocks should provide extremely specific and detailed so user can get as much information as there is available.
    The MediaBlocks are there to further elaborate or clarify the already discussed knowledge in TextBlocks, so 
    user interest is kept. 
    The Overlay tags in MediaBlocks should be extremely specific and detailed so user can get as much information as there is available, and learns like a student from you.
    Thoughtfull Feedbacks and Feedforwards in the FeedbackAndFeedforwardBlock should be made,
    and give assignments in the SelfAssessmentTextBlock so the user uses critical thinking skills and is encouraged to
    think about how much of the "Learning Objectives" has been achieved.
    ***
    ***YOU WILL BE PENALISED IF:
    The TextBlocks has information that you do NOT elaborate in detail, if detail is available in "Input Documents".
    The MediaBlocks are NOT used in complimentary manner to the information in TextBlocks.
    ***
    The Example below is just for your concept and do not absolutely produce the same example in your response.
    Ensure that TextBlocks and MediaBlocks provide comprehensive information directly related to the LearningObjectives and ContentAreas. Adjust the number and length of these blocks based on the necessary detail required for students to fully understand and accurately reproduce the information presented.    
    You are creative in the manner of choosing the number of TextBlocks and MediaBlocks to give best quality information to students. In each branch you are free to choose TextBlocks or MediaBlocks or both or multiple of them to convey best quality, elaborative information.
    Make sure students learn from these TextBlocks and MediaBlocks.

    \nOverview Sample structure of the Simulation Scenario\n
    ScenarioType
    LearningObjectives
    ContentAreas
    Briefing
    Start
    TextBlock (Welcome message to the scenario)
    MediaBlock (To give visualized option to select simulation choices path)
    SimpleBranchingBlock (To select from a choice of choices (Branches) )
    Branch 1,2,3... (DIVISIBLE type containing path to other Branches) => with its TextBlock/s or None,MediaBlock/s or None, Branching Block (Conditional Branching) / Branching Block (Simple Branching)
    Branch 1,2,3... (NON-DIVISIBLE type that are end of scenario branches not divisible further) =>with its TextBlock/s or None,MediaBlock/s or None, Goal Block, FeedbackAndFeedforwardBlock, Debriefing, Reflection
    Branch 1,2,3... (NON-DIVISIBLE-MERGE type to link scenario branches when one story directly advances another branch's storyline) =>with its TextBlock/s or None,MediaBlock/s or None, JumpBlock
    \nEnd of Overview structure\n

    SAMPLE EXAMPLE
{{
    "ScenarioType": "Simulation Pedagogy Scenario",
    "LearningObjectives": [
        "",
        ""
    ],
    "ContentAreas": [
        ""
    ],
    "Start": "Emergency Evacuation from a Building on Fire",
    "Blocks": [
        {{"branch_blocks":"1,2,3"}},
        {{
            "id": "1",
            "type": "Briefing",
            "title": "Welcome message to the scenario",
            "description": "Formulate a comprehensive Briefing about what is coming in the simulation, why and purpose of all this. Guide the student with this Brieifing block."
        }},
        {{
            "id": "2",
            "timer": "optional value 00:00 mm:ss, for example 05:00",
            "type": "Media Block",
            "title": "Choosing Your Exit",
            "mediaType": "360-image/Image (Preferred)/Video etc. e.g. 360-image",
            "description": "Visualize the emergency scenario on the 5th floor with escape options outlined through interactive tags.",
            "overlayTags": [
                {{
                    "textTag/imageTag/videoTag e.g.textTag": "Explain and teach the students using this tag the different aspects of the information for this media block. Also give instructions here of how to shoot these medias e.g.Main Elevator: An arrow pointing towards the elevator with a caption: 'To the Ground Floor'."
                }},
                {{
                    "textTag/imageTag/videoTag e.g.textTag": "e.g.Staircase: An arrow pointing left with a caption: 'To the Lower Floors'."
                }}
            ]
        }},
        {{
            "id": "3",
            "timer": "optional value 00:00 mm:ss, for example 00:30",
            "type": "Branching Block (Simple Branching)",
            "title": "A situation where a choice needs to be selected",
            "branches": {{
                "3.1": "Some Choice",
                "3.2": "Some Choice",
                "3.3": "Some Choice",
                "and so on...":  "...",
            }}
        }},
        {{
            "id": "3.1",
            "type": "Branch (DIVISIBLE)",
            "blocks": [
                {{"branch_blocks":"3.1.1,3.1.2,3.1.3,3.1.4,3.1.5"}},
                {{
                    "id": "3.1.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Text Block",
                    "title": "",
                    "description": ""
                }},
                {{
                    "id": "3.1.2",
                    "Purpose": "Mandatory",
                    "type": "Goal Block",
                    "title": "",
                    "description": "",
                    "score": -10
                }},
                {{
                    "id": "3.2.3",
                    "Purpose": "Mandatory",
                    "type": "FeedbackAndFeedforwardBlock",
                    "Feedback": "",
                    "Feedforward": ""
                }},
                {{
                    "id": "3.1.4",
                    "Purpose": "Mandatory",
                    "type": "Debriefing",
                    "description": ""
                }},
                {{
                    "id": "3.1.5",
                    "Purpose": "Mandatory",
                    "type": "Reflection",
                    "description": ""
                }}
            ]
        }},
        {{
            "id": "3.2",
            "type": "Branch (DIVISIBLE)",
            "blocks": [
                {{"branch_blocks":"3.2.1,3.2.2"}},
                {{
                    "id": "3.2.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Text Block",
                    "title": "",
                    "description": ""
                }},
                {{
                    "id": "3.2.2",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "Continue Down or Seek Another Exit?",
                    "questionText": "The stairs are congested and progress is slow. Do you continue or look for another exit?",
                    "proceedToBranchForEachAnswer": [
                        {{
                            "text": "Continue down the stairs.",
                            "proceedToBlock": "3.2.2.1"
                        }},
                        {{
                            "text": "Go back and use the emergency exit.",
                            "proceedToBlock": "3.2.2.2"
                        }}
                    ]
                }},
                {{
                    "id": "3.2.2.1",
                    "type": "Branch (NON-DIVISIBLE)",
                    "blocks": [
                        {{"branch_blocks":"3.2.2.1.1,3.2.2.1.2,3.2.2.1.3,3.2.2.1.4,3.2.2.1.5"}},
                        {{
                            "id": "3.2.2.1.1",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.1.2",
                            "Purpose": "Mandatory",
                            "type": "Goal Block",
                            "title": "",
                            "description": "",
                            "score": 5
                        }},
                        {{
                            "id": "3.2.2.2.3",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.2.2.1.4",
                            "Purpose": "Mandatory",
                            "type": "Debriefing",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.1.5",
                            "Purpose": "Mandatory",
                            "type": "Reflection",
                            "description": ""
                        }}
                    ]
                }},
                {{
                    "id": "3.2.2.2 Branch (NON-DIVISIBLE)",
                    "type": "Branch",
                    "blocks": [
                        {{"branch_blocks":"3.2.2.2.1,3.2.2.2.2,3.2.2.2.3,3.2.2.2.4,3.2.2.2.5"}},
                        {{
                            "id": "3.2.2.2.1",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.2.2",
                            "Purpose": "Mandatory",
                            "type": "Goal Block",
                            "title": "Successful and Swift Evacuation",
                            "description": "",
                            "score": 20
                        }},
                        {{
                            "id": "3.2.2.2.3",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.2.2.2.4",
                            "Purpose": "Mandatory",
                            "type": "Debriefing",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.2.5",
                            "Purpose": "Mandatory",
                            "type": "Reflection",
                            "description": ""
                        }}
                    ]
                }}
            ]
        }}
    ],
}}
    SAMPLE EXAMPLE END

    \n\nANOTHER SAMPLE EXAMPLE START\n\n
{{
    "ScenarioType": "Simulation Pedagogy Scenario",
    "LearningObjectives": [
        "",
        ""
    ],
    "ContentAreas": [
        ""
    ],
    "Start": "Emergency Evacuation from a Building on Fire",
    "Blocks": [
        {{"branch_blocks":"1,2,3"}},
        {{
            "id": "1",
            "type": "Briefing",
            "title": "Welcome to the scenario and proceedings",
            "description": "Formulate a comprehensive Briefing about what is coming in the simulation, why and purpose of all this. Guide the student with this Brieifing block."
        }},
        {{
            "id": "2",
            "timer": "optional value 00:00 mm:ss",
            "type": "Media Block",
            "title": "Choosing Your Exit",
            "mediaType": "360-image/Image (Preferred)/Video e.g. 360-image",
            "description": "Visualize the emergency scenario on the 5th floor with escape options outlined through interactive tags.",
            "overlayTags": [
                {{
                    "textTag/imageTag/videoTag e.g.textTag": "Explain and teach the students using this tag the different aspects of the information for this media block. Also give instructions here of how to shoot these medias e.g.Main Elevator: An arrow pointing towards the elevator with a caption: 'To the Ground Floor'."
                }},
                {{
                    "textTag/imageTag/videoTag e.g.textTag": "e.g.Staircase: An arrow pointing left with a caption: 'To the Lower Floors'."
                }}
            ]
        }},
        {{
            "id": "3",
            "timer": "optional value 00:00 mm:ss",
            "type": "Branching Block (Simple Branching)",
            "title": "A situation where a choice needs to be selected",
            "branches": {{
                "3.1": "Some Choice",
                "3.2": "Some Choice",
            }}
        }},
        {{
            "id": "3.1",
            "type": "Branch (NON-DIVISIBLE-MERGE)",
            "blocks": [
                {{"branch_blocks":"3.1.1,3.1.2,3.1.3,3.1.4"}},
                {{
                    "id": "3.1.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Text Block",
                    "title": "",
                    "description": ""
                }},
                {{
                    "id": "3.1.2",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Media Block",
                    "title": "",
                    "mediaType": "360-image/Image (Preferred)/Video e.g. 360-image",
                    "description": "",
                    "overlayTags": [
                        {{
                            "textTag/imageTag/videoTag": "overlayTags detailed content and instructions for producing them for the media type of 360-image/Image (Preferred)/Video selected"
                        }}
                    ]
                }},
                {{
                    "id": "3.1.3",
                    "Purpose": "Mandatory",
                    "type": "FeedbackAndFeedforwardBlock",
                    "Feedback": "",
                    "Feedforward": ""
                }},
                {{
                    "id": "3.1.4",
                    "Purpose": "Mandatory if One Branch's story leads to connecting with another Branch's block",
                    "type": "JumpBlock",
                    "title": "",
                    "proceedToBlock": "3.2.2.1"
                }}
            ]
        }},
        {{
            "id": "3.2",
            "type": "Branch (DIVISIBLE)",
            "blocks": [
                {{"branch_blocks":"3.2.1,3.2.2"}},
                {{
                    "id": "3.2.1",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Media Block",
                    "title": "",
                    "mediaType": "360-image/Image (Preferred)/Video e.g. 360-image",
                    "description": "",
                    "overlayTags": [
                        {{
                            "textTag/imageTag/videoTag": ""
                        }}
                    ]
                }},
                {{
                    "id": "3.2.2",
                    "timer": "optional value 00:00 mm:ss",
                    "type": "Branching Block (Simple Branching)",
                    "title": "A situation where a choice needs to be selected",
                    "branches": {{
                        "3.2.2.1": "Some Choice",
                        "3.2.2.2": "Some Choice",
                        "and so on choices...": "",
                    }}
                }},
                {{
                    "id": "3.2.2.1",
                    "type": "Branch (NON-DIVISIBLE)",
                    "blocks": [
                        {{"branch_blocks":"3.2.2.1.1,3.2.2.1.2,3.2.2.1.3,3.2.2.1.4,3.2.2.1.5,3.2.2.1.6"}},
                        {{
                            "id": "3.2.2.1.1",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.1.2",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.1.3",
                            "Purpose": "Mandatory",
                            "type": "Goal Block",
                            "title": "",
                            "description": "",
                            "score": 5
                        }},
                        {{
                            "id": "3.2.2.2.4",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.2.2.1.5",
                            "Purpose": "Mandatory",
                            "type": "Debriefing",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.1.6",
                            "Purpose": "Mandatory",
                            "type": "Reflection",
                            "description": ""
                        }}
                    ]
                }},
                {{
                    "id": "3.2.2.2 Branch (NON-DIVISIBLE)",
                    "type": "Branch",
                    "blocks": [
                        {{"branch_blocks":"3.2.2.2.1,3.2.2.2.2,3.2.2.2.3,3.2.2.2.4,3.2.2.2.5,3.2.2.2.6,3.2.2.2.7"}},
                        {{
                            "id": "3.2.2.2.1",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.2.2",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Text Block",
                            "title": "",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.2.3",
                            "timer": "optional value 00:00 mm:ss",
                            "type": "Media Block",
                            "title": "",
                            "mediaType": "360-image/Image (Preferred)/Video e.g. 360-image",
                            "description": "",
                            "overlayTags": [
                                {{
                                    "textTag/imageTag/videoTag": ""
                                }}
                            ]
                        }},
                        {{
                            "id": "3.2.2.2.4",
                            "Purpose": "Mandatory",
                            "type": "Goal Block",
                            "title": "Successful and Swift Evacuation",
                            "description": "",
                            "score": 20
                        }},
                        {{
                            "id": "3.2.2.2.5",
                            "Purpose": "Mandatory",
                            "type": "FeedbackAndFeedforwardBlock",
                            "Feedback": "",
                            "Feedforward": ""
                        }},
                        {{
                            "id": "3.2.2.2.6",
                            "Purpose": "Mandatory",
                            "type": "Debriefing",
                            "description": ""
                        }},
                        {{
                            "id": "3.2.2.2.7",
                            "Purpose": "Mandatory",
                            "type": "Reflection",
                            "description": ""
                        }}
                    ]
                }}
            ]
        }}
    ],
}}
    \n\nEND OF SAMPLE EXAMPLE\n\n
    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable. 
    You Prefer to make simulation such that a choice may lead to a consequnece that may lead to more choice or choices that may lead to more consequences, evetually reaching the end of the scenario.
    Give concise, relevant, clear, and descriptive instructions as you are an educational provider that has expertise 
    in molding asked information into the said block structure to teach and instruct students.     

    NEGATIVE PROMPT: Do not respond outside the JSON format.   

    Chatbot (Tone of a teacher instructing and teaching student in great detail):"""
)


prompt_LO_CA = PromptTemplate(
    input_variables=["input_documents","human_input"],
    template="""
    Based on the information provided in 'Human Input' and 'Input Documents', you are going to generate 
    Learning Objectives and Content Areas in a JSON format. Make sure the both Learning Objectives and Content Areas
    are specifically relevant to the query of 'Human Input'. 
    Lets suppose the 'Human Input' asks for a course to be created for Driving a Car. 
    And the 'Input Documents' has information for both Driving a Car and Repairing a Car. 
    Then, you should only give the Learning Objectives and Content Areas about Driving a Car only
    since the 'Human Input' asked you only about this topic.

    Do not give any Learning Objectives or Content Areas based on information
    not present in the 'Input Documents'. You have to just strictly keep the Learning Objectives and Content Areas
    limited and specific to the information asked by 'Human Input' AND present in the 'Input Documents'; and nothing outside it.
    ***Stick strictly to the information given in the 'Input Documents' provided to you.
    The 'Human Input' decides what information to collect from the 'Input Documents' to create Learning Objectives
    and Content Areas.***

    *DIRE WARNING: The number of points of Learning Objectives and Content Areas can be different.
    The Example below is only given for context of format and absolutely NOT for the fact that you 
    generate same number of points as given in the Example for the Learning Objectives and Content Areas. 
    Learning Objectives and Content Areas can have only 1 point or more points, 
    all depends on the amount of information present in the 'Input Documents'
    and the query pertaining to it by the human in the 'Human Input'.*
    
    \nExample\n
    {{
    "LearningObjectives": [
        "1. Recognize the Signs and Symptoms of a Heart Attack: Learners will be able to identify both typical and atypical signs of a heart attack, understanding that symptoms can vary widely among individuals.\n2. Emergency Response Procedures: Learners will understand the steps to take in both scenarios where the patient is unconscious and conscious, including the use of DRSABCD (Danger, Response, Send for help, Airway, Breathing, CPR, Defibrillation)."
    ],
    "ContentAreas": [
        "1. Introduction to Heart Attacks: Overview of what constitutes a heart attack, including the physiological underpinnings and the importance of quick response.\n2. Identifying Symptoms: Detailed review of both common and less common symptoms of heart attacks, with emphasis on variations by gender, age, and pre-existing conditions.\n3. First Aid Steps: Step-by-step guide for responding to a heart attack in various situations (unconscious vs. conscious patients)."
    ]
    }}
    \nExample End\n

    'Human Input': {human_input}
    'Input Documents': {input_documents}
    Chatbot:"""
)

def PRODUCE_LEARNING_OBJ_COURSE(query, docsearch, llm):
    print("PRODUCE_LEARNING_OBJ_COURSE Initiated!")
    docs = docsearch.similarity_search(query, k=3)
    docs_main = " ".join([d.page_content for d in docs])
    chain = LLMChain(prompt=prompt_LO_CA, llm=llm)

    return chain, docs_main, query

def RE_SIMILARITY_SEARCH(query, docsearch):
    print("PRODUCE_LEARNING_OBJ_COURSE Initiated!")
    docs = docsearch.similarity_search(query, k=3)
    docs_main = " ".join([d.page_content for d in docs])

    return docs_main


def TALK_WITH_RAG(scenario, content_areas, learning_obj, query, docs_main, llm):
    print("TALK_WITH_RAG Initiated!")
    # if we are getting docs_main already from the process_data flask route then comment, else
    # UNcomment if you want more similarity_searching based on Learning obj and content areas!
    # docs = docsearch.similarity_search(query, k=3)
    # docs_main = " ".join([d.page_content for d in docs])

         
    if scenario == "linear":
        print("SCENARIO ====prompt_linear",scenario)
        chain = LLMChain(prompt=prompt_linear, llm=llm)
        response = chain({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})

    elif scenario == "branched":
        print("SCENARIO ====branched",scenario)
        # summarized first, then response
        llm_setup = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)
        chain1 = LLMChain(prompt=prompt_branched_setup,llm=llm_setup)
        response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
        print("Response 1 is::",response1['text'])

        chain = LLMChain(prompt=prompt_branched,llm=llm)
        response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})

    elif scenario == "simulation":
        print("SCENARIO ====prompt_simulation_pedagogy",scenario)
        # summarized first, then response
        llm_setup = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)
        chain1 = LLMChain(prompt=prompt_simulation_pedagogy_setup,llm=llm_setup)
        response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
        print("Response 1 is::",response1['text'])

        chain = LLMChain(prompt=prompt_simulation_pedagogy,llm=llm)
        response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})

    elif scenario == "gamified":
        print("SCENARIO ====prompt_gamified",scenario)
        llm_setup = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)
        chain1 = LLMChain(prompt=prompt_gamified_setup,llm=llm_setup)
        response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
        print("Response 1 is::",response1['text'])

        # chain2 = LLMChain(prompt=prompt_gamified_simple,llm=llm_setup)
        # response2 = chain2({"response_of_bot_simple": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
        # print("Response 2 is::",response2['text'])

        chain = LLMChain(prompt=prompt_gamified_json,llm=llm)
        response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
        print("Response 3 is::",response['text'])

    elif scenario == "auto":
        print("SCENARIO ====PROMPT",scenario)
        # chain = prompt | llm | {f"{llm_memory}": RunnablePassthrough()}
        

        ### SEMANTIC ROUTES LOGIC ###
        llm_auto = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0.4, max_tokens=32)
        llm_auto_chain = LLMChain(prompt=promptSelector, llm=llm_auto)
        title_scenario_output = llm_auto_chain.run({"input_documents": docs_main, "human_input": query})
        print(title_scenario_output)

        linear_select = Route(
        name="linear",
        utterances=[
            "Linear Scenario",
            "linear scenario",
            "linear",
            "Based on the provided 'Human Input' and 'Document data' related to First Aid, the most suitable scenario for developing a course is the Linear scenario.",
        ],
        )
        escaperoom_select = Route(
            name="gamified",
            utterances=[
                "gamified",
                "Gamified Scenario",
                "gamified scenario",
                "Based on the provided 'Human Input' and 'Document data' related to First Aid, the most suitable scenario for developing a course is the Gamified scenario.",
            ],
        )
        simulation_select = Route(
            name="simulation",
            utterances=[
                "simulation scenario",
                "Simulation Scenario",
                "simulation",
                "Based on the provided 'Human Input' and 'Document data' related to First Aid, the most suitable scenario for developing a course is the Simulation scenario.",
            ],
        )
        selfexploratory_select = Route(
            name="branched",
            utterances=[
                "Branched",
                "branched scenario",
                "Branched Scenario",
                "Based on the provided 'Human Input' and 'Document data' related to First Aid, the most suitable scenario for developing a course is the Branched scenario.",
            ],
        )

        routes = [linear_select, escaperoom_select, simulation_select, selfexploratory_select]
        encoder = OpenAIEncoder()
        rl = RouteLayer(encoder=encoder, routes=routes,llm=llm_auto)
        selected = rl(title_scenario_output)
        print("Semantic Scenario Selected of NAME",selected.name)
        ############################

        if selected.name == 'gamified':

            llm_setup = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)
            chain1 = LLMChain(prompt=prompt_gamified_setup,llm=llm_setup)
            response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
            print("Response 1 is::",response1['text'])

            # chain = LLMChain(prompt=prompt_gamified_setup,llm=llm_setup)
            # response2 = chain({"response_of_bot_simple": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
            # print("Response 2 is::",response2['text'])

            chain = LLMChain(prompt=prompt_gamified_json,llm=llm)
            response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
            print("Response 3 is::",response['text'])

        elif selected.name == 'linear':
            chain = LLMChain(prompt=prompt_linear, llm=llm)
            response = chain({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})

        elif selected.name == 'simulation':
            llm_setup = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)
            chain1 = LLMChain(prompt=prompt_simulation_pedagogy_setup,llm=llm_setup)
            response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
            print("Response 1 is::",response1['text'])

            chain = LLMChain(prompt=prompt_simulation_pedagogy,llm=llm)
            response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
        
        elif selected.name == 'branched':
            llm_setup = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)
            chain1 = LLMChain(prompt=prompt_branched_setup,llm=llm_setup)
            response1 = chain1({"input_documents": docs_main,"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})
            print("Response 1 is::",response1['text'])

            chain = LLMChain(prompt=prompt_branched,llm=llm)
            response = chain({"response_of_bot": response1['text'],"human_input": query,"content_areas": content_areas,"learning_obj": learning_obj})


    ### Static Query###   
    # docs_page_contents = [doc.page_content for doc in docs]
    # docs_whole_contents = docsearch.similarity_search("Title name of object, device or theory of this document", k=1)
    # static_query = """For what object, device or theory is this document written for? Only write the short title name for it.
    # Use information obtained from user relevant specific search results {docs_page_contents} and the general document {docs_whole_contents}, to 
    # give a short title name suggestion and do not describe anything."""

    # llm_title = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, max_tokens=32)
    # prompt_title = PromptTemplate(
    #     input_variables=["docs_whole_contents","docs_page_contents"],
    #     template=static_query)
    # llm_title_chain = LLMChain(prompt=prompt_title, llm=llm_title)
    # title_name_output = llm_title_chain.run({"docs_whole_contents": docs_whole_contents, "docs_page_contents": docs_page_contents})
    # print(title_name_output)
    # # subject_name = title_name_output
    # from langchain.chains import create_extraction_chain
    # # Schema
    # schema_title = {
    #     "properties": {
    #         "subject_name": {"type": "string"},
    #     },
    #     "required": ["subject_name"],
    # }
    # # Run chain
    # llm_title_extraction_chain = create_extraction_chain(schema_title, llm_title)
    # subject_name = llm_title_extraction_chain.run(title_name_output)
    # print(subject_name)  
 
    return response

