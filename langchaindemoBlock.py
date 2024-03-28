import soundfile as sf
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
from langchain.chains.question_answering import load_qa_chain
from reportlab.pdfgen import canvas 
import matplotlib
import os
from flask import Flask, render_template, request, session, flash, get_flashed_messages
from io import BytesIO
from semantic_router import Route, RouteLayer
from semantic_router.encoders import OpenAIEncoder
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.chains import ConversationChain

#for the optimized scenario chat with a bit of flexible chat and working langchain memory



# llm = ChatOpenAI(model="gpt-3.5-turbo-16k-0613", temperature=0.1, streaming=True, callbacks=[StreamingStdOutCallbackHandler()])
# template = """You are a chatbot having a conversation with a human.

# {chat_history}
# Human: {user_input}
# Chatbot:"""

# def llm_conversation(user_input):
#     response_bot = chain.predict(user_input=user_input)
#     return response_bot

def RAG(pdf_files):
    all_texts = []
    for pdf_file in pdf_files:
        text = ''
        pdf_reader = PdfReader(pdf_file)
        for i, page in enumerate(pdf_reader.pages):
            text_instant = page.extract_text()
            if text_instant:
                text += text_instant
            all_texts.append(text)

    combined_text = ' '.join(all_texts)

    # chunking
    text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = 1024,
    chunk_overlap  = 64,
    length_function = len,
    )
    texts = text_splitter.split_text(combined_text)
    embeddings = OpenAIEmbeddings()
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

    Escape Room: A gamified environment that encourages applying subject knowledge to escape a scenario, 
    enhancing investigative and critical thinking skills.
    Linear: Straightforward, step-by-step training on a topic, ending with quizzes to evaluate understanding.
    Self Exploratory: A sandbox-style experience where users can explore various aspects of a topic at 
    their own pace, including subtopics with quizzes. 
    Simulation: A decision-making driven gamified learning experience, where choices lead to different 
    outcomes, encouraging exploration of consequences. 

    'Human Input': ({human_input})
    'Input Documents': ({input_documents})
        
    EXAMPLE BOT REPLIES 
    Your reply should be one of the below (Depends on what you find suitable to be selected):
    Bot: Escape Room Scenario
    Bot: Simulation Scenario
    Bot: Linear Scenario
    Bot: Self Exploratory Scenario
    """
)

prompt = PromptTemplate(
    input_variables=["input_documents","human_input","subject_name", "chat_history"],
    template="""
    You need to follow the method to take a user's course content ideas and their specific requirements, 
    then reformat these into a structured JSON format that aligns with examples or templates previously given. 
    This process will ensure the course structure is clearly organized and presented in a consistent, 
    machine-readable format, suitable for various educational topics.

    To accomplish this, YOU will:

    1. Take the "Human Input" which represents the course content ideas and specific requirements from the user.
    2. Utilize "Input Documents" that might include detailed course outlines, module descriptions, and instructional materials relevant to the course topic.
    3. Generate a JSON-formatted course structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.

    You either automatically choose one of the four scenario types for creating courses or in-case the 'Human Input'
    specifies, you select that scenario type to create the course.

    Here is an introduction to these four types of scenario types for course building. Based on the 
    'Input Documents' content, you can decide what course is best to be used if you are asked to automatically
    select scenario type to create the course.
    Escape Room: A gamified environment that encourages applying subject knowledge to escape a scenario, 
    enhancing investigative and critical thinking skills. In escape room scenario, apart from using the 
    Linear: Straightforward, step-by-step training on a topic, ending with quizzes to evaluate understanding.
    Self Exploratory: A sandbox-style experience where users can explore various aspects of a topic at 
    their own pace, including subtopics with quizzes. 
    Simulation: A decision-making driven gamified learning experience, where choices lead to different 
    outcomes, encouraging exploration of consequences. 

    The courses are built using blocks, each having its own parameters.
    Block types include: 
    'Text Block': with timer, title, and description
    'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'Question Block': with Question text, answers, correct answer, wrong answer message
    'Branching Block'(includes three types, choose one of the three): 
    'Simple Branching' with Title, Timer, Proceed To Branch List  
    'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
    'Explore More Branching' with Title, Proceed To Branch List
    'Goal Block': Title, Score
    'Jump Block': with title, Proceed To Block___

    SCENARIO UNQIUENESS:
    Self Exploratory: 'Explore More Branching' (First the 'Simple Branching' is used
    to devide the course into sub-topics branches for user to select and continue. At the end of each 
    sub-topic Branch the 'Explore More Branching' gives user the choice to either return to main branch
    or give quiz for that sub-topic branch)


    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.   
    \nEXAMPLES\n
    \n\nLinear Scenario\n\n
{{
  "ScenarioType": "Linear Scenario",
  "LearningObjectives": [
    "Identify and understand the common and atypical symptoms of heart attacks, emphasizing the variability among different individuals.",
    "Execute immediate and appropriate first aid responses for someone experiencing a heart attack, including ensuring comfort and administering aspirin when appropriate.",
    "Apply the DRSABCD action plan effectively in heart attack emergencies to enhance patient survival chances before medical help arrives.",
    "Assess and respond correctly to scenario-based questions on heart attack symptoms and first aid, reinforcing knowledge application in real-world situations."
  ],
  "Start": "Introduction to First Aid for Heart Attacks",
  "Blocks": [
    {{
      "id": "1",
      "type": "Text Block",
      "title": "Understanding Heart Attacks",
      "description": "A heart attack is a life-threatening medical emergency. Knowing the signs and immediate actions can save lives. This course will guide you through recognizing heart attack symptoms, administering first aid, and understanding the importance of immediate medical intervention."
    }},
    {{
      "id": "2",
      "type": "Media Block",
      "title": "Recognizing Heart Attack Symptoms",
      "mediaType": "Image",
      "description": "An infographic showing common and atypical signs of a heart attack. Symptoms can vary greatly among individuals and might include chest discomfort, shortness of breath, and more.",
      "overlayTags": [
        {{
          "textTag": "Chest Pain - Described as tightness, heaviness, or squeezing."
        }},
        {{
          "audioTag": "Atypical Symptoms - Includes shortness of breath, nausea, and faintness."
        }},
        {{
          "videoTag": "Symptom Variability - Understanding how symptoms can differ among different populations."
        }}
      ]
    }},
    {{
      "id": "3",
      "type": "Question Block",
      "questionText": "Which of the following is NOT a common symptom of a heart attack?",
      "answers": [
        "Chest pain",
        "Shortness of breath",
        "Sudden dizziness",
        "Rapid hair growth"
      ],
      "correctAnswer": "Rapid hair growth",
      "wrongAnswerMessage": "Incorrect. Remember, common symptoms include chest pain, shortness of breath, and sudden dizziness. Hair growth is unrelated to heart attacks."
    }},
    {{
      "id": "4",
      "type": "Text Block",
      "title": "Immediate Actions During a Heart Attack",
      "description": "Quick and appropriate actions can be critical. Learn the steps to assist someone experiencing a heart attack, from ensuring their comfort to administering aspirin, and when to perform CPR."
    }},
    {{
      "id": "5",
      "type": "Media Block",
      "title": "First Aid for Heart Attack",
      "mediaType": "Video",
      "description": "A step-by-step guide video on what to do if someone is having a heart attack, including DRSABCD protocol, how to assist with medication, and ensuring the patient is in a comfortable position.",
      "overlayTags": [
        {{
          "textTag": "DRSABCD - A reminder of the steps to take in an emergency."
        }},
        {{
          "videoTag": "Administering Aspirin - How and when to give aspirin safely."
        }},
        {{
          "audioTag": "Comforting the Patient - The importance of reassurance."
        }}
      ]
    }},
    {{
      "id": "6",
      "type": "Question Block",
      "questionText": "If the patient is conscious and experiencing heart attack symptoms, what is one of the first actions you should take?",
      "answers": [
        "Give them water",
        "Encourage them to keep moving",
        "Help them to sit or lie down and rest",
        "Leave them to find help"
      ],
      "correctAnswer": "Help them to sit or lie down and rest",
      "wrongAnswerMessage": "Incorrect. The first step is to help the patient rest in a comfortable position to reduce strain on the heart."
    }},
    {{
      "id": "7",
      "type": "Goal Block",
      "title": "Heart Attack First Aid Mastery",
      "score": 10
    }}
  ]
}}
    \n\nLinear Scenario End\n\n

    \n\nEscape Room Scenario\n\n
{{
    "ScenarioType": "Escape Room Scenario",
    "LearningObjectives": [
        "Recognize and select appropriate materials in the wilderness that can be used as tinder, kindling, and fuel for starting a fire.",
        "Understand the importance of choosing the right tinder for ignition, distinguishing between materials that will ignite easily and those that won’t.",
        "Learn how to safely and effectively prepare a fire pit, ensuring it’s positioned away from flammable materials and structures.",
        "Master the correct way to arrange tinder, kindling, and larger logs to successfully start and maintain a fire.",
        "Emphasize the importance of fire safety in the wilderness to prevent wildfires and ensure personal safety.",
        "Apply critical thinking and problem-solving skills to navigate through challenges and make informed decisions in survival scenarios."
    ],
    "Start": "Survival Skills: Starting a Fire",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Emergency Situation: Lost in the Woods",
            "description": "You find yourself lost in a dense forest as night approaches. The temperature is dropping, and you need to start a fire for warmth and to signal for help. Can you navigate through the challenges to successfully start a fire?"
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "title": "Identifying Your Resources",
            "mediaType": "360-image",
            "description": "A 360-degree view of your surroundings in the forest. You can see various materials that could be useful for starting a fire.",
            "overlayTags": [
                {{
                    "textTag": "Dry Leaves - Potential tinder."
                }},
                {{
                    "textTag": "Twigs and Branches - Small and medium-sized for kindling."
                }},
                {{
                    "textTag": "Large Logs - For sustaining the fire once started."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choosing Your Tinder",
            "branches": {{
                "3.1": "Use Wet Leaves (Incorrect Path)",
                "3.2": "Use Dry Leaves (Correct Path)"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
               {{
"id": "3.1.1",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3"
        }}]}},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Text Block",
                    "title": "Gathering Tinder",
                    "description": "You've chosen dry leaves, an excellent choice for tinder due to their quick ignition. Now, gather them cautiously to avoid dampening."
                }},
                {{
                    "id": "3.2.2",
                    "type": "Media Block",
                    "title": "Preparing the Fire Pit",
                    "mediaType": "Image",
                    "description": "Instructions on clearing a space on the ground to create a fire pit, ensuring it's away from overhead and surrounding flammable materials.",
                    "overlayTags": [
                        {{
                            "textTag": "Clearing Space - Ensure a safe area for the fire."
                        }},
                        {{
                            "textTag": "Safety First - Keep away from flammable materials."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "How to Arrange Your Tinder and Kindling?",
                    "timer": "30 seconds",
                    "questionText": "Do you place the twigs and branches over the dry leaves or under them?",
                    "proceedToBranchForEachAnswer": [
                        {{
                            "text": "Over the dry leaves.",
                            "proceedToBlock": "3.2.3.1"
                        }},
                        {{
                            "text": "Under the dry leaves.",
                            "proceedToBlock": "3.2.3.2"
                        }}
                    ]
                }}
            ]
        }},
        {{
            "id": "3.2.3.1",
            "blocks": [
               {{
"id": "3.2.3.1.1",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3.2.3"
        }}]}},
        {{
            "id": "3.2.3.2",
            "blocks": [
                {{
                    "id": "3.2.3.2.1",
                    "type": "Text Block",
                    "title": "Igniting the Fire",
                    "description": "With the tinder and kindling correctly arranged, it's time to ignite your fire. You can use a flint, matches, or a lighter if you have one. Patience and persistence are key."
                }},
                {{
                    "id": "3.2.3.2.2",
                    "type": "Goal Block",
                    "title": "Fire Successfully Started! Congratulations! You've successfully started a fire and learned crucial survival skills. Remember, practice makes perfect, and these skills could be life-saving in real situations",
                    "score": 10
                }}
            ]
        }}
    ]
}}    
    \n\nEscape Room Scenario End\n\n

    \n\nSelf Exploratory Scenario\n\n    
{{
    "ScenarioType": "Self Exploratory Scenario",
    "LearningObjectives": [
        "Grasp the principles of how wind turbines and solar panels generate electricity.",
        "Identify the differences between wind and solar energy, including their mechanisms and applications.",
        "Acknowledge how renewable energy reduces carbon emissions and combats climate change.",
        "Discover advancements in renewable energy technologies, such as transparent and flexible solar panels.",
        "Learn about the installation, maintenance, and efficiency of solar energy systems in homes and businesses.",
        "Assess the impact of renewable energy on reducing global carbon footprint and promoting sustainability."
    ],
    "Start": "Introduction to Renewable Energy",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Welcome to Renewable Energy Exploration",
            "description": "Discover the shift towards renewable energy to combat climate change. This journey explores different renewable sources, their workings, and their impacts on our planet."
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "title": "A Glimpse into Renewable Energy Sources",
            "mediaType": "360-image",
            "description": "An immersive 360-degree image capturing an expansive green field, dotted with the leading technologies in renewable energy: gleaming solar panels and majestic wind turbines stand as testaments to sustainable power generation.",
            "overlayTags": [
                {{
                    "textTag": "Solar Panels - Harnessing sunlight to produce clean energy."
                }},
                {{
                    "textTag": "Wind Turbines - Converting wind into electrical power through innovation."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Renewable Energy Path",
            "branches": {{
                "3.1": "Wind Energy Exploration",
                "3.2": "Solar Energy Exploration"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
                {{
                    "id": "3.1.1",
                    "type": "Media Block",
                    "title": "How Wind Turbines Work",
                    "mediaType": "Image",
                    "description": "This image offers a deep dive into the anatomy of a wind turbine through a detailed cross-section animation, illuminating the intricate mechanics from rotor to generator.",
                    "overlayTags": [
                        {{
                            "videoTag": "Turbine Mechanics - An animated insight into the components that capture wind."
                        }},
                        {{
                            "textTag": "Energy Conversion - The journey from wind to electricity explained visually."
                        }}
                    ]
                }},
                {{
                    "id": "3.1.2",
                    "type": "Media Block",
                    "title": "Environmental Benefits of Wind Energy",
                    "mediaType": "Image",
                    "description": "An enlightening infographic that lays bare the environmental advantages of wind energy, comparing the minimal CO2 emissions to the higher rates associated with fossil fuels, underscoring the clean, sustainable future wind power promises.",
                    "overlayTags": [
                        {{
                            "imageTag": "Emission Reduction - Graphical depiction of CO2 savings with wind energy."
                        }},
                        {{
                            "textTag": "Renewable Benefits - Highlighting the eco-positive impacts of adopting wind power."
                        }}
                    ]
                }},
                {{
                    "id": "3.1.3",
                    "type": "Explore More Branching",
                    "title": "Explore More About Renewable Energies?",
                    "branches": {{
                        "3.1.3.1": "Yes",
                        "3.1.3.2": "No"
                    }}
                }}
            ]
        }},
        {{
            "id": "3.1.3.1",
            "blocks": [
                {{
                    "id": "3.1.3.1.1",
                    "type": "Jump Block",
                    "title": "Yes",
                    "proceedToBlock": "3"
                }}
            ]
        }},
        {{
            "id": "3.1.3.2",
            "blocks": [
                {{
                    "id": "3.1.3.2.1",
                    "type": "Question Block",
                    "questionText": "What part of the wind turbine captures wind energy?",
                    "answers": [
                        "Blades",
                        "Rotor"
                    ],
                    "correctAnswer": "Blades",
                    "wrongAnswerMessage": "The blades are the correct answer, as they capture and convert wind energy into mechanical power."
                }},
                {{
                    "id": "3.1.3.2.2",
                    "type": "Question Block",
                    "questionText": "True or False: Wind energy produces greenhouse gases during electricity generation.",
                    "answers": [
                        "True",
                        "False"
                    ],
                    "correctAnswer": "False",
                    "wrongAnswerMessage": "False is correct, wind energy is a clean source that doesn't emit greenhouse gases during electricity generation."
                }},
                {{
                    "id": "3.1.3.2.3",
                    "type": "Goal Block",
                    "title": "Wind Energy course knowledge achieved",
                    "score": 10
                }}
            ]
        }},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Media Block",
                    "title": "Solar Panels at Work",
                    "mediaType": "Video",
                    "description": "This video elucidates the marvel of the photovoltaic effect within solar panels, from sunlight capture to electricity generation, demystifying the science with every frame.",
                    "overlayTags": [
                        {{
                            "imageTag": "Photovoltaic Cells - Converting sunlight into electrical energy."
                        }},
                        {{
                            "textTag": "Solar Efficiency - Exploring how solar panels maximize sunlight capture."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.2",
                    "type": "Media Block",
                    "title": "Solar Energy for Homes and Businesses",
                    "mediaType": "Image",
                    "description": "This case study presents a solar-powered smart home, emblematic of modern sustainability, showcasing how residential and commercial spaces can thrive on solar energy, emphasizing efficiency and cost savings.",
                    "overlayTags": [
                        {{
                            "imageTag": "Smart Home Energy - A virtual showcase of solar-powered living."
                        }},
                        {{
                            "textTag": "Cost Savings - The financial benefits of solar energy for homes and businesses illuminated."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "type": "Media Block",
                    "title": "Installing Solar Panels",
                    "mediaType": "Video",
                    "description": "A comprehensive video guide walks you through the installation of rooftop solar panels, covering every step from tool selection to safety measures, ensuring an efficient setup for maximum energy capture.",
                    "overlayTags": [
                        {{
                            "textTag": "Installation Process - Step-by-step video instructions for mounting solar panels."
                        }},
                        {{
                            "videoTag": "Maintenance Tips - Best practices to keep your solar panels performing at their peak."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.4",
                    "type": "Media Block",
                    "title": "Future Solar Innovations",
                    "mediaType": "Image",
                    "description": "Dive into the future with visualizations of cutting-edge solar technologies, including transparent solar panels for windows and flexible solar panels for varied applications, spotlighting the endless possibilities of solar innovation.",
                    "overlayTags": [
                        {{
                            "videoTag": "Next-Gen Solar - Exploring advancements in solar technology."
                        }},
                        {{
                            "textTag": "Innovative Applications - How new solar technologies can revolutionize energy generation."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.5",
                    "type": "Explore More Branching",
                    "title": "Ready to Explore More About Renewable Energies?",
                    "branches": {{
                        "3.2.5.1": "Yes",
                        "3.2.5.2": "No"
                    }}
                }}
            ]
        }},
        {{
            "id": "3.2.5.1",
            "blocks": [
                {{
                    "id": "3.2.5.1.1",
                    "type": "Jump Block",
                    "title": "Yes",
                    "proceedToBlock": "3"
                }}
            ]
        }},
        {{
            "id": "3.2.5.2",
            "blocks": [
                {{
                    "id": "3.2.5.2.1",
                    "type": "Question Block",
                    "questionText": "Solar panels are most efficient in which type of climate?",
                    "answers": [
                        "Sunny and cool",
                        "Hot and humid"
                    ],
                    "correctAnswer": "Sunny and cool",
                    "wrongAnswerMessage": "Solar panels perform best in sunny and cool climates, maximizing efficiency."
                }},
                {{
                    "id": "3.2.5.2.2",
                    "type": "Question Block",
                    "questionText": "True or False: Solar panels cannot produce electricity on cloudy days.",
                    "answers": [
                        "True",
                        "False"
                    ],
                    "correctAnswer": "False",
                    "wrongAnswerMessage": "False is correct. Solar panels can still generate electricity on cloudy days, though at reduced efficiency."
                }},
                {{
                    "id": "3.2.5.2.3",
                    "type": "Goal Block",
                    "title": "Solar Energy course knowledge achieved",
                    "score": 10
                }}
            ]
        }}
    ]
}}
    \n\nSelf Exploratory Scenario End\n\n

    \n\nSimulation Scenario\n\n        
{{
    "ScenarioType": "Simulation Scenario",
    "LearningObjectives": [
        "Recognize the importance of quick and informed decision-making during a fire emergency.",
        "Identify fire safety protocols for avoidance of elevators and the use of staircases for evacuation."
    ],
    "Start": "Emergency Evacuation from a Building on Fire",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Emergency Alert",
            "description": "You are on the 5th floor of a 10-story office building when the fire alarm starts blaring. The loudspeakers announce a fire on the 7th floor. You must quickly decide how to exit the building."
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "timer": "60 seconds",
            "title": "Choosing Your Exit",
            "mediaType": "360-degree image",
            "description": "You're presented with a crucial decision amidst the urgency of an evacuation on the 5th floor. This 360-degree view lays out your escape options: the risky main elevator, or the reliable staircase for a downward exit. Each choice carries its implications for safety and speed.",
            "overlayTags": [
                {{
                    "textTag": "'Main Elevator': An arrow pointing towards the elevator with a caption: 'To the Ground Floor'."
                }},
                {{
                    "textTag": "'Staircase': An arrow pointing left with a caption: 'To the Lower Floors'."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Exit",
            "timer": "45 seconds",
            "branches": {{
                "3.1": "Main Elevator",
                "3.2": "Staircase"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
                {{
                    "id": "3.1.1",
                    "type": "Text Block",
                    "timer": "60 seconds",
                    "title": "Elevator Failure",
                    "description": "The elevator stops between the 4th and 5th floors due to the fire emergency systems. You are stuck until rescued by firefighters."
                }},
                {{
                    "id": "3.1.2",
                    "type": "Goal Block",
                    "title": "Stuck in the Elevator. Using the elevator during a fire resulted in failure to exit the building timely.",
                    "score": -10
                }}
            ]
        }},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Text Block",
                    "timer": "120 seconds",
                    "title": "Descending the Stairs",
                    "description": "You quickly head down the staircase, which is crowded and slow-moving due to the number of people trying to exit."
                }},
                {{
                    "id": "3.2.2",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "Continue Down or Seek Another Exit?",
                    "timer": "45 seconds",
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
                }}
            ]
        }},
        {{
            "id": "3.2.2.1",
            "blocks": [
                {{
                    "id": "3.2.2.1.1",
                    "type": "Text Block",
                    "timer": "90 seconds",
                    "title": "Safe, But Slow Exit",
                    "description": "You eventually reach the ground floor, but precious time was lost, and the situation could have worsened, especially, a high risk of stampede is there."
                }},
                {{
                    "id": "3.2.2.1.2",
                    "type": "Goal Block",
                    "title": "Evacuated via Stairs. You safely exited the building, but with a time penalty for not choosing the fastest route.",
                    "score": 5
                }}
            ]
        }},
        {{
            "id": "3.2.2.2",
            "blocks": [
                {{
                    "id": "3.2.2.2.1",
                    "type": "Text Block",
                    "timer": "60 seconds",
                    "title": "Emergency Exit to Safety",
                    "description": "You use the emergency exit and quickly descend the fire escape, reaching the ground safely and swiftly."
                }},
                {{
                    "id": "3.2.2.2.2",
                    "type": "Goal Block",
                    "title": "Successful and Swift Evacuation. You chose the safest and fastest route to exit the building during the fire ",
                    "score": 20
                }}
            ]
        }}
    ]
}}
    \n\nSimulation Scenario End\n\n
    \nEXAMPLES\n
    'Human Input': {human_input}, 
    'Input Documents':{input_documents},

    'Chat History': {chat_history},

    'Chatbot':"""
)

prompt_linear = PromptTemplate(
    input_variables=["input_documents","human_input","subject_name", "chat_history"],
    template="""
    You need to follow the method to take a user's course content ideas and their specific requirements, 
    then reformat these into a structured JSON format that aligns with example or template previously given. 
    This process will ensure the course structure is clearly organized and presented in a consistent, 
    machine-readable format, suitable for various educational topics.

    To accomplish this, YOU will:

    1. Take the "Human Input" which represents the course content ideas and specific requirements from the user.
    2. Utilize "Input Documents" that might include detailed course outlines, module descriptions, and instructional materials relevant to the course topic.
    3. Generate a JSON-formatted course structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.
 
    The courses are built using blocks, each having its own parameters.
    Block types include: 
    'Text Block': with timer(optional), title, and description
    'Media Block': with timer(optional), title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'Question Block': with Question text, answers, correct answer, wrong answer message
    'Goal Block': Title, Score

    Linear Scenario: Is Straightforward, step-by-step, detailed and very specific training on a topic, 
    ending with quizz (series of Question Blocks) to evaluate understanding, all in JSON format. 
    Text Blocks, should elaborate in detail the methods/ techniques/ steps/ instructions/ information of
    the subject. Conclude with key takeaways or critical points learners should remember. 
    This ensures clarity and emphasis on the most important concepts. Include insights of the subject or 
    step of the instruction you are on.

    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    Use Text Blocks to explain all the information in a step-by-step manner. If you think is needed,
    add Media Blocks that act as a complement to the Text Block content. Then add Series of Question Blocks in the
    the end to test user's knowledge about the subject. Question Block can be at intermediate stage as well.
    The Goal Block ends the scenario.
    ***

    \n\nEXAMPLE FORMAT FOR EACH SCENARIO\n\n
    \nLINEAR SCENARIO:\n
{{
  "ScenarioType": "Linear Scenario",
  "LearningObjectives": [
    "Identify and understand the common and atypical symptoms of heart attacks, emphasizing the variability among different individuals.",
    "Execute immediate and appropriate first aid responses for someone experiencing a heart attack, including ensuring comfort and administering aspirin when appropriate.",
    "Apply the DRSABCD action plan effectively in heart attack emergencies to enhance patient survival chances before medical help arrives.",
    "Assess and respond correctly to scenario-based questions on heart attack symptoms and first aid, reinforcing knowledge application in real-world situations."
  ],
  "Start": "Introduction to First Aid for Heart Attacks",
  "Blocks": [
    {{
      "id": "1",
      "type": "Text Block",
      "title": "Understanding Heart Attacks",
      "description": "A heart attack is a life-threatening medical emergency. Knowing the signs and immediate actions can save lives. This course will guide you through recognizing heart attack symptoms, administering first aid, and understanding the importance of immediate medical intervention."
    }},
    {{
      "id": "2",
      "type": "Media Block",
      "title": "Recognizing Heart Attack Symptoms",
      "mediaType": "Image",
      "description": "An infographic showing common and atypical signs of a heart attack. Symptoms can vary greatly among individuals and might include chest discomfort, shortness of breath, and more.",
      "overlayTags": [
        {{
          "textTag": "Chest Pain - Described as tightness, heaviness, or squeezing."
        }},
        {{
          "audioTag": "Atypical Symptoms - Includes shortness of breath, nausea, and faintness."
        }},
        {{
          "videoTag": "Symptom Variability - Understanding how symptoms can differ among different populations."
        }}
      ]
    }},
    {{
      "id": "3",
      "type": "Question Block",
      "questionText": "Which of the following is NOT a common symptom of a heart attack?",
      "answers": [
        "Chest pain",
        "Shortness of breath",
        "Sudden dizziness",
        "Rapid hair growth"
      ],
      "correctAnswer": "Rapid hair growth",
      "wrongAnswerMessage": "Incorrect. Remember, common symptoms include chest pain, shortness of breath, and sudden dizziness. Hair growth is unrelated to heart attacks."
    }},
    {{
      "id": "4",
      "type": "Text Block",
      "title": "Immediate Actions During a Heart Attack",
      "description": "Quick and appropriate actions can be critical. Learn the steps to assist someone experiencing a heart attack, from ensuring their comfort to administering aspirin, and when to perform CPR."
    }},
    {{
      "id": "5",
      "type": "Media Block",
      "title": "First Aid for Heart Attack",
      "mediaType": "Video",
      "description": "A step-by-step guide video on what to do if someone is having a heart attack, including DRSABCD protocol, how to assist with medication, and ensuring the patient is in a comfortable position.",
      "overlayTags": [
        {{
          "textTag": "DRSABCD - A reminder of the steps to take in an emergency."
        }},
        {{
          "videoTag": "Administering Aspirin - How and when to give aspirin safely."
        }},
        {{
          "audioTag": "Comforting the Patient - The importance of reassurance."
        }}
      ]
    }},
    {{
      "id": "6",
      "type": "Question Block",
      "questionText": "If the patient is conscious and experiencing heart attack symptoms, what is one of the first actions you should take?",
      "answers": [
        "Give them water",
        "Encourage them to keep moving",
        "Help them to sit or lie down and rest",
        "Leave them to find help"
      ],
      "correctAnswer": "Help them to sit or lie down and rest",
      "wrongAnswerMessage": "Incorrect. The first step is to help the patient rest in a comfortable position to reduce strain on the heart."
    }},
    {{
      "id": "7",
      "type": "Goal Block",
      "title": "Heart Attack First Aid Mastery",
      "score": 10
    }}
  ]
}}
    \n\nEND OF EXAMPLE\n\n

    'Human Input': {human_input},
    'Input Documents': ({input_documents}) => Use this information content to mold the response that adheres to the format of this scenario.
    Chat history: {chat_history}

    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable. 
    Give concise, relevant, clear, and descriptive instructions as you are a course creator that has expertise 
    in molding asked information into the linear scenario structure.     

    NEGATIVE PROMPT: Do not respond outside the JSON format.   

    Chatbot:"""
)

prompt_selfexploratory = PromptTemplate(
    input_variables=["input_documents","human_input","subject_name", "chat_history"],
    template="""
    You need to follow the method to take a user's course content ideas and their specific requirements, 
    then reformat these into a structured JSON format that aligns with example or template previously given. 
    This process will ensure the course structure is clearly organized and presented in a consistent, 
    machine-readable format, suitable for various educational topics.

    To accomplish this, YOU will:

    1. Take the "Human Input" which represents the course content ideas and specific requirements from the user.
    2. Utilize "Input Documents" that might include detailed course outlines, module descriptions, and instructional materials relevant to the course topic.
    3. Generate a JSON-formatted course structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.
 
    The courses are built using blocks, each having its own parameters.
    Block types include: 
    'Text Block': with title, and description
    'Media Block': with title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'Question Block': with Question text, answers, correct answer, wrong answer message
    'Branching Block'(includes two types, choose one of the two): 
    'Simple Branching' with Title, Proceed To Branch List  
    'Explore More Branching' with Title, Proceed To Branch List
    'Goal Block': Title, Score
    'Jump Block': with title, Proceed To Block___

    Self Exploratory: ALWAYS INCLUDE THE 'Explore More Branching' Block in this scenario! 
    First the 'Simple Branching' is used to devide the course into sub-topics branches for user to select and 
    continue. At the end of each sub-topic Branch; after all the instructions and knowledge given via Text Blocks
    and Media Blocks; the 'Explore More Branching' Block gives user the choice by 'Yes' or 'No' to either return to main branch
    to select other sub-topic or give quiz for that sub-topic branch. 
    Text Blocks, should elaborate in detail the methods/ techniques/ steps/ instructions/ information of
    the subject. Conclude with key takeaways or critical points learners should remember. 
    This ensures clarity and emphasis on the most important concepts. Include insights of the subject or 
    step of the instruction you are on.
    
    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    1. Use 'Simple Branching' Block type to devide the course into sub-topics for user to choose from.
    2. Use 'Explore More Branching' Block type gives user choices of:
    'Yes'=> return to main branch to select other sub-topic or sub-topics for study.
    'No'=> forwards user to quiz by giving series of questions for that sub-topic branch and the 
    branches always end with 'Goal Block' after such series of questions when user selects 'No'.
    ***

    \n\nSELF EXPLORATORY SCENARIO:\n\n
{{
    "ScenarioType": "Self Exploratory Scenario",
    "LearningObjectives": [
        "Grasp the principles of how wind turbines and solar panels generate electricity.",
        "Identify the differences between wind and solar energy, including their mechanisms and applications.",
        "Acknowledge how renewable energy reduces carbon emissions and combats climate change.",
        "Discover advancements in renewable energy technologies, such as transparent and flexible solar panels.",
        "Learn about the installation, maintenance, and efficiency of solar energy systems in homes and businesses.",
        "Assess the impact of renewable energy on reducing global carbon footprint and promoting sustainability."
    ],
    "Start": "Introduction to Renewable Energy",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Welcome to Renewable Energy Exploration",
            "description": "Discover the shift towards renewable energy to combat climate change. This journey explores different renewable sources, their workings, and their impacts on our planet."
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "title": "A Glimpse into Renewable Energy Sources",
            "mediaType": "360-image",
            "description": "An immersive 360-degree image capturing an expansive green field, dotted with the leading technologies in renewable energy: gleaming solar panels and majestic wind turbines stand as testaments to sustainable power generation.",
            "overlayTags": [
                {{
                    "textTag": "Solar Panels - Harnessing sunlight to produce clean energy."
                }},
                {{
                    "textTag": "Wind Turbines - Converting wind into electrical power through innovation."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Renewable Energy Path",
            "branches": {{
                "3.1": "Wind Energy Exploration",
                "3.2": "Solar Energy Exploration"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
                {{
                    "id": "3.1.1",
                    "type": "Media Block",
                    "title": "How Wind Turbines Work",
                    "mediaType": "Image",
                    "description": "This image offers a deep dive into the anatomy of a wind turbine through a detailed cross-section animation, illuminating the intricate mechanics from rotor to generator.",
                    "overlayTags": [
                        {{
                            "videoTag": "Turbine Mechanics - An animated insight into the components that capture wind."
                        }},
                        {{
                            "textTag": "Energy Conversion - The journey from wind to electricity explained visually."
                        }}
                    ]
                }},

                {{
                    "id": "3.1.2",
                    "type": "Explore More Branching",
                    "title": "Explore More About Renewable Energies?",
                    "branches": {{
                        "3.1.2.1": "Yes",
                        "3.1.2.2": "No"
                    }}
                }}
            ]
        }},
        {{
            "id": "3.1.2.1",
            "blocks": [
                {{
                    "id": "3.1.2.1.1",
                    "type": "Jump Block",
                    "title": "Yes",
                    "proceedToBlock": "3"
                }}
            ]
        }},
        {{
            "id": "3.1.2.2",
            "blocks": [
                {{
                    "id": "3.1.2.2.1",
                    "type": "Question Block",
                    "questionText": "What part of the wind turbine captures wind energy?",
                    "answers": [
                        "Blades",
                        "Rotor"
                    ],
                    "correctAnswer": "Blades",
                    "wrongAnswerMessage": "The blades are the correct answer, as they capture and convert wind energy into mechanical power."
                }},

                {{
                    "id": "3.1.2.2.2",
                    "type": "Goal Block",
                    "title": "Wind Energy course knowledge achieved",
                    "score": 10
                }}
            ]
        }},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Media Block",
                    "title": "Solar Panels at Work",
                    "mediaType": "Video",
                    "description": "This video elucidates the marvel of the photovoltaic effect within solar panels, from sunlight capture to electricity generation, demystifying the science with every frame.",
                    "overlayTags": [
                        {{
                            "imageTag": "Photovoltaic Cells - Converting sunlight into electrical energy."
                        }},
                        {{
                            "textTag": "Solar Efficiency - Exploring how solar panels maximize sunlight capture."
                        }}
                    ]
                }},

                {{
                    "id": "3.2.2",
                    "type": "Media Block",
                    "title": "Future Solar Innovations",
                    "mediaType": "Image",
                    "description": "Dive into the future with visualizations of cutting-edge solar technologies, including transparent solar panels for windows and flexible solar panels for varied applications, spotlighting the endless possibilities of solar innovation.",
                    "overlayTags": [
                        {{
                            "videoTag": "Next-Gen Solar - Exploring advancements in solar technology."
                        }},
                        {{
                            "textTag": "Innovative Applications - How new solar technologies can revolutionize energy generation."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "type": "Explore More Branching",
                    "title": "Ready to Explore More About Renewable Energies?",
                    "branches": {{
                        "3.2.3.1": "Yes",
                        "3.2.3.2": "No"
                    }}
                }}
            ]
        }},
        {{
            "id": "3.2.3.1",
            "blocks": [
                {{
                    "id": "3.2.3.1.1",
                    "type": "Jump Block",
                    "title": "Yes",
                    "proceedToBlock": "3"
                }}
            ]
        }},
        {{
            "id": "3.2.3.2",
            "blocks": [
                {{
                    "id": "3.2.3.2.1",
                    "type": "Question Block",
                    "questionText": "Solar panels are most efficient in which type of climate?",
                    "answers": [
                        "Sunny and cool",
                        "Hot and humid"
                    ],
                    "correctAnswer": "Sunny and cool",
                    "wrongAnswerMessage": "Solar panels perform best in sunny and cool climates, maximizing efficiency."
                }},
                {{
                    "id": "3.2.5.2.3",
                    "type": "Goal Block",
                    "title": "Solar Energy course knowledge achieved",
                    "score": 10
                }}
            ]
        }}
    ]
}}
    \n\nEND OF EXAMPLE\n\n

    'Human Input': {human_input},
    'Input Documents': ({input_documents}) => Use this information content to mold the response that adheres to the format of this scenario.
    Chat history: {chat_history}

    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.
    Give concise, relevant, clear, and descriptive instructions as you are a course creator that has expertise 
    in molding asked information into the self exploratory scenario structure.   

    NEGATIVE PROMPT: Do not respond outside the JSON format.   

    Chatbot:"""
)

prompt_simulation = PromptTemplate(
    input_variables=["input_documents","human_input","subject_name", "chat_history"],
    template="""
    You need to follow the method to take a user's course content ideas and their specific requirements, 
    then reformat these into a structured JSON format that aligns with example or template previously given. 
    This process will ensure the course structure is clearly organized and presented in a consistent, 
    machine-readable format, suitable for various educational topics.

    To accomplish this, YOU will:

    1. Take the "Human Input" which represents the course content ideas and specific requirements from the user.
    2. Utilize "Input Documents" that might include detailed course outlines, module descriptions, and instructional materials relevant to the course topic.
    3. Generate a JSON-formatted course structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.
 
    The courses are built using blocks, each having its own parameters.
    Block types include: 
    'Text Block': with timer, title, and description
    'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'Branching Block'(includes two types, choose one of the two): 
    'Simple Branching' with Title, Timer, Proceed To Branch List  
    'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
    'Goal Block': Title, Score

    Simulation Scenario: Create gamified, decision-driven courses using various blocks, 
    each with specific parameters. Your goal is to design an engaging scenario 
    with multiple endings, influenced by user choices.

    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    You storify any given data and are able to design a scenario where user choices impact the narrative, leading to various endings. 
    Use Branching Blocks to present decision points, allowing for a dynamic path through the content. 
    Choices may conclude the story or lead to further Branching Blocks, culminating in diverse outcomes 
    showcased by Goal Blocks. Exercise creativity in the number of choices and narrative paths.
    This Scenario is not complete without using Branching Blocks that offers choices and consequent
    multiple endings of the storified course.
    ***

    \n\nEXAMPLE FORMAT FOR EACH SCENARIO\n\n
    \nSIMULATION SCENARIO:\n
{{
    "ScenarioType": "Simulation Scenario",
    "LearningObjectives": [
        "Recognize the importance of quick and informed decision-making during a fire emergency.",
        "Identify fire safety protocols for avoidance of elevators and the use of staircases for evacuation."
    ],
    "Start": "Emergency Evacuation from a Building on Fire",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Emergency Alert",
            "description": "You are on the 5th floor of a 10-story office building when the fire alarm starts blaring. The loudspeakers announce a fire on the 7th floor. You must quickly decide how to exit the building."
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "timer": "60 seconds",
            "title": "Choosing Your Exit",
            "mediaType": "360-degree image",
            "description": "You're presented with a crucial decision amidst the urgency of an evacuation on the 5th floor. This 360-degree view lays out your escape options: the risky main elevator, or the reliable staircase for a downward exit. Each choice carries its implications for safety and speed.",
            "overlayTags": [
                {{
                    "textTag": "'Main Elevator': An arrow pointing towards the elevator with a caption: 'To the Ground Floor'."
                }},
                {{
                    "textTag": "'Staircase': An arrow pointing left with a caption: 'To the Lower Floors'."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Exit",
            "timer": "45 seconds",
            "branches": {{
                "3.1": "Main Elevator",
                "3.2": "Staircase"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
                {{
                    "id": "3.1.1",
                    "type": "Text Block",
                    "timer": "60 seconds",
                    "title": "Elevator Failure",
                    "description": "The elevator stops between the 4th and 5th floors due to the fire emergency systems. You are stuck until rescued by firefighters."
                }},
                {{
                    "id": "3.1.2",
                    "type": "Goal Block",
                    "title": "Stuck in the Elevator. Using the elevator during a fire resulted in failure to exit the building timely.",
                    "score": -10
                }}
            ]
        }},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Text Block",
                    "timer": "120 seconds",
                    "title": "Descending the Stairs",
                    "description": "You quickly head down the staircase, which is crowded and slow-moving due to the number of people trying to exit."
                }},
                {{
                    "id": "3.2.2",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "Continue Down or Seek Another Exit?",
                    "timer": "45 seconds",
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
                }}
            ]
        }},
        {{
            "id": "3.2.2.1",
            "blocks": [
                {{
                    "id": "3.2.2.1.1",
                    "type": "Text Block",
                    "timer": "90 seconds",
                    "title": "Safe, But Slow Exit",
                    "description": "You eventually reach the ground floor, but precious time was lost, and the situation could have worsened, especially, a high risk of stampede is there."
                }},
                {{
                    "id": "3.2.2.1.2",
                    "type": "Goal Block",
                    "title": "Evacuated via Stairs. You safely exited the building, but with a time penalty for not choosing the fastest route.",
                    "score": 5
                }}
            ]
        }},
        {{
            "id": "3.2.2.2",
            "blocks": [
                {{
                    "id": "3.2.2.2.1",
                    "type": "Text Block",
                    "timer": "60 seconds",
                    "title": "Emergency Exit to Safety",
                    "description": "You use the emergency exit and quickly descend the fire escape, reaching the ground safely and swiftly."
                }},
                {{
                    "id": "3.2.2.2.2",
                    "type": "Goal Block",
                    "title": "Successful and Swift Evacuation. You chose the safest and fastest route to exit the building during the fire ",
                    "score": 20
                }}
            ]
        }}
    ]
}}
    \n\nEND OF EXAMPLE\n\n

    'Human Input': {human_input},
    'Input Documents': ({input_documents}) => Use this information content to mold the response that adheres to the format of this scenario.
    Chat history: {chat_history}
    
    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.   
    Give concise, relevant, clear, and descriptive instructions as you are a course creator that has expertise 
    in molding asked information into the simulation scenario structure.   

    NEGATIVE PROMPT: Do not respond outside the JSON format.   

    Chatbot:"""
)

prompt_escaperoom = PromptTemplate(
    input_variables=["input_documents","human_input","subject_name", "chat_history"],
    template="""
    You need to follow the method to take a user's course content ideas and their specific requirements, 
    then reformat these into a structured JSON format that aligns with example or template previously given. 
    This process will ensure the course structure is clearly organized and presented in a consistent, 
    machine-readable format, suitable for various educational topics.

    To accomplish this, YOU will:

    1. Take the "Human Input" which represents the course content ideas and specific requirements from the user.
    2. Utilize "Input Documents" that might include detailed course outlines, module descriptions, and instructional materials relevant to the course topic.
    3. Generate a JSON-formatted course structure. This JSON structure will be crafted following the guidelines and format exemplified in the provided examples, which serve as a template for organizing the course content efficiently and logically.
 
    The courses are built using blocks, each having its own parameters.
    Block types include: 
    'Text Block': with timer, title, and description
    'Media Block': with timer, title, Media Type (Text, Image, 360-image, Video, audio), Description of the Media used, Overlay tags used as hotspots on the Media as text, video or audio
    'Branching Block'(includes two types, choose one of the two): 
    'Simple Branching' with Title, Timer, Proceed To Branch List  
    'Conditional Branching' with Title, Timer, Question text, answers, Proceed To Brach for each answer
    'Goal Block': Title, Score
    'Jump Block': with title, Proceed To Block___

    Escape Room: Here, the Text Blocks and Media Blocks are used to give user the information
    and knowledge about a topic in the form of clues. Based on these clue of information, the Branching Block
    gives user a choice to select. That choice is either correct or incorrect. In case, the user selects the incorrect
    choice, the user is routed via the 'Jump Block' back to the decision Branching Block. On the contrary,
    if the user selects the correct choice, it leads to a Branch having more Text Blocks and Media Blocks, 
    giving further information in the form of clues and deviding into correct or incorrect choices, similarly. Untill
    the finally, situation is completed by escaping that situation and Goal block is used to give confirmation of 
    escaping and being successfull.  
    Text Blocks, should elaborate in detail the methods/ techniques/ steps/ instructions/ information of
    the subject. Conclude with key takeaways or critical points learners should remember. 
    This ensures clarity and emphasis on the most important concepts. Include insights of the subject or 
    step of the instruction you are on.
    
    ***KEEP IN MIND THE LOGIC THAT OPERATES THIS SCENARIO IS IN:
    This scenario always uses either the Simple Branching Block or Conditional Branching Block
    to give user the option to choose only from one of the two choices. One choice is Correct and
    other one choice is Incorrect. Both are written in brackets only for information for instructor
    who is making this course and will be deleted by instructor later.
    The Incorrect choice leads to 'Jump Block' that leads its way back to the deviding Branch Block.
    The Correct choice leads to a branch that may or may not have more Text or Media Blocks to give 
    clues and information and leads to more branches of Correct and Incorrect Choices, until the Goal Block
    is reached which represents and successfully escaped room situation and points reward.
    ***

    \n\nEXAMPLE FORMAT FOR EACH SCENARIO\n\n
    \nESCAPE ROOM SCENARIO:\n
{{
    "ScenarioType": "Escape Room Scenario",
    "LearningObjectives": [
        "Recognize and select appropriate materials in the wilderness that can be used as tinder, kindling, and fuel for starting a fire.",
        "Understand the importance of choosing the right tinder for ignition, distinguishing between materials that will ignite easily and those that won’t.",
        "Learn how to safely and effectively prepare a fire pit, ensuring it's positioned away from flammable materials and structures.",
        "Master the correct way to arrange tinder, kindling, and larger logs to successfully start and maintain a fire.",
        "Emphasize the importance of fire safety in the wilderness to prevent wildfires and ensure personal safety.",
        "Apply critical thinking and problem-solving skills to navigate through challenges and make informed decisions in survival scenarios."
    ],
    "Start": "Survival Skills: Starting a Fire",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Emergency Situation: Lost in the Woods",
            "description": "You find yourself lost in a dense forest as night approaches. The temperature is dropping, and you need to start a fire for warmth and to signal for help. Can you navigate through the challenges to successfully start a fire?"
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "title": "Identifying Your Resources",
            "mediaType": "360-image",
            "description": "A 360-degree view of your surroundings in the forest. You can see various materials that could be useful for starting a fire.",
            "overlayTags": [
                {{
                    "textTag": "Dry Leaves - Potential tinder."
                }},
                {{
                    "textTag": "Twigs and Branches - Small and medium-sized for kindling."
                }},
                {{
                    "textTag": "Large Logs - For sustaining the fire once started."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choosing Your Tinder",
            "branches": {{
                "3.1": "Use Wet Leaves (Incorrect Path)",
                "3.2": "Use Dry Leaves (Correct Path)"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
               {{
"id": "3.1.1",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3"
        }}]}},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Text Block",
                    "title": "Gathering Tinder",
                    "description": "You've chosen dry leaves, an excellent choice for tinder due to their quick ignition. Now, gather them cautiously to avoid dampening."
                }},
                {{
                    "id": "3.2.2",
                    "type": "Media Block",
                    "title": "Preparing the Fire Pit",
                    "mediaType": "Image",
                    "description": "Instructions on clearing a space on the ground to create a fire pit, ensuring it's away from overhead and surrounding flammable materials.",
                    "overlayTags": [
                        {{
                            "textTag": "Clearing Space - Ensure a safe area for the fire."
                        }},
                        {{
                            "textTag": "Safety First - Keep away from flammable materials."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "How to Arrange Your Tinder and Kindling?",
                    "timer": "30 seconds",
                    "questionText": "Do you place the twigs and branches over the dry leaves or under them?",
                    "proceedToBranchForEachAnswer": [
                        {{
                            "text": "Over the dry leaves.(Incorrect Path)",
                            "proceedToBlock": "3.2.3.1"
                        }},
                        {{
                            "text": "Under the dry leaves.(Correct Path)",
                            "proceedToBlock": "3.2.3.2"
                        }}
                    ]
                }}
            ]
        }},
        {{
            "id": "3.2.3.1",
            "blocks": [
               {{
"id": "3.2.3.1.1",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3.2.3"
        }}]}},
        {{
            "id": "3.2.3.2",
            "blocks": [
                {{
                    "id": "3.2.3.2.1",
                    "type": "Text Block",
                    "title": "Igniting the Fire",
                    "description": "With the tinder and kindling correctly arranged, it's time to ignite your fire. You can use a flint, matches, or a lighter if you have one. Patience and persistence are key."
                }},
                {{
                    "id": "3.2.3.2.2",
                    "type": "Goal Block",
                    "title": "Fire Successfully Started! Congratulations! You've successfully started a fire and learned crucial survival skills. Remember, practice makes perfect, and these skills could be life-saving in real situations",
                    "score": 10
                }}
            ]
        }}
    ]
}} 
    \n\nEND OF EXAMPLE\n\n

    'Human Input': {human_input},
    'Input Documents': ({input_documents}) => Use this information content to mold the response that adheres to the format of this scenario.
    Chat history: {chat_history}
    
    !!!ATTENTION!!!
    Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.  
    Give concise, relevant, clear, and descriptive instructions as you are a course creator that has expertise 
    in molding asked information into the escape room scenario structure.

    NEGATIVE PROMPT: Do not respond outside the JSON format.     
    
    Chatbot:"""
)
# chain = load_qa_chain(
#     llm=llm, chain_type="stuff", prompt=prompt
# )

def TALK_WITH_RAG(query, docsearch, llm,scenario):
    print("TALK_WITH_RAG Initiated!")
    docs = docsearch.similarity_search(query, k=3)
    docs_main = " ".join([d.page_content for d in docs])

    # chain = load_qa_chain(
    #     llm=llm, chain_type="stuff", prompt=prompt
    # )

    #Memory Make
    memory = ConversationBufferWindowMemory(memory_key="chat_history",input_key="human_input",k=5,return_messages=True)
    # Iterate over each pair of user and bot messages
    # for pair in chating_history:
    #     user_message = pair['user']
    #     bot_message = pair['bot']
    #     # Save the context of each conversation pair to memory
    #     # memory.save_context({"input": user_message}, {"output": bot_message})
    #     memory.chat_memory.add_user_message(user_message)
    #     memory.chat_memory.add_ai_message(bot_message)
    # # llm_memory = memory.load_memory_variables({})
         
    if scenario == "linear":
        print("SCENARIO ====prompt_linear",scenario)
        chain = LLMChain(prompt=prompt_linear, llm=llm,memory=memory)
    elif scenario == "self_exploratory":
        print("SCENARIO ====prompt_selfexploratory",scenario)
        chain = LLMChain(prompt=prompt_selfexploratory, llm=llm,memory=memory)
    elif scenario == "simulation":
        print("SCENARIO ====prompt_simulation",scenario)
        chain = LLMChain(prompt=prompt_simulation, llm=llm,memory=memory)
    elif scenario == "escape_room":
        print("SCENARIO ====prompt_escaperoom",scenario)
        chain = LLMChain(prompt=prompt_escaperoom, llm=llm,memory=memory)
    elif scenario == "auto":
        print("SCENARIO ====PROMPT",scenario)
        # chain = prompt | llm | {f"{llm_memory}": RunnablePassthrough()}
        
        print(memory.load_memory_variables({}))

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
            name="escape_room",
            utterances=[
                "escape room",
                "Escape Room",
                "escape_room",
                "escape-room",
                "escape room scenario",
                "Based on the provided 'Human Input' and 'Document data' related to First Aid, the most suitable scenario for developing a course is the Escape Room scenario.",
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
            name="self_exploratory",
            utterances=[
                "Self Exploratory",
                "self exploratory",
                "self-exploratory",
                "self exploratory scenario",
                "Based on the provided 'Human Input' and 'Document data' related to First Aid, the most suitable scenario for developing a course is the Self Exploratory scenario.",
            ],
        )

        routes = [linear_select, escaperoom_select, simulation_select, selfexploratory_select]
        encoder = OpenAIEncoder()
        rl = RouteLayer(encoder=encoder, routes=routes,llm=llm_auto)
        selected = rl(title_scenario_output)
        print("Semantic Scenario Selected of NAME",selected.name)
        ############################

        if selected.name == 'escape_room':
            chain = LLMChain(prompt=prompt_escaperoom, llm=llm,memory=memory)
        elif selected.name == 'linear':
            chain = LLMChain(prompt=prompt_linear, llm=llm,memory=memory)
        elif selected.name == 'simulation':
            chain = LLMChain(prompt=prompt_simulation, llm=llm,memory=memory)
        elif selected.name == 'self_exploratory':
            chain = LLMChain(prompt=prompt_selfexploratory, llm=llm,memory=memory)

    
    ### Static Query###   
    docs_page_contents = [doc.page_content for doc in docs]
    docs_whole_contents = docsearch.similarity_search("Title name of object, device or theory of this document", k=1)
    static_query = """For what object, device or theory is this document written for? Only write the short title name for it.
    Use information obtained from user relevant specific search results {docs_page_contents} and the general document {docs_whole_contents}, to 
    give a short title name suggestion and do not describe anything."""

    llm_title = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, max_tokens=32)
    prompt_title = PromptTemplate(
        input_variables=["docs_whole_contents","docs_page_contents"],
        template=static_query)
    llm_title_chain = LLMChain(prompt=prompt_title, llm=llm_title)
    title_name_output = llm_title_chain.run({"docs_whole_contents": docs_whole_contents, "docs_page_contents": docs_page_contents})
    print(title_name_output)
    # subject_name = title_name_output
    from langchain.chains import create_extraction_chain
    # Schema
    schema_title = {
        "properties": {
            "subject_name": {"type": "string"},
        },
        "required": ["subject_name"],
    }
    # Run chain
    llm_title_extraction_chain = create_extraction_chain(schema_title, llm_title)
    subject_name = llm_title_extraction_chain.run(title_name_output)
    print(subject_name)   
    print(docs_main)
    return chain, docs_main, query, subject_name


def GENERATE_GRAPHML(bot_last_reply,llmsx):
    print("This is last reply",bot_last_reply)

    GRAPHML_PROMPT_ESCAPE_ROOM = PromptTemplate(input_variables=['text'], template="""You are a JSON intelligence helping a human track knowledge by giving providing them with
    JSON having various blocks representing information about all
    relevant people, things, concepts, etc. and integrating them with your knowledge stored within your weights as well as that stored in the JSON format.
    \n\nEXAMPLE\n\n
    \nESCAPE ROOM SCENARIO:\n
    Scenario Type: Escape Room Scenario
    Learning Objectives: 
    -	Recognize and select appropriate materials in the wilderness that can be used as tinder, kindling, and fuel for starting a fire.
    -	Understand the importance of choosing the right tinder for ignition, distinguishing between materials that will ignite easily and those that won’t.
    -	Learn how to safely and effectively prepare a fire pit, ensuring its positioned away from flammable materials and structures.
    -	Master the correct way to arrange tinder, kindling, and larger logs to successfully start and maintain a fire.
    -	Emphasize the importance of fire safety in the wilderness to prevent wildfires and ensure personal safety.
    -	Apply critical thinking and problem-solving skills to navigate through challenges and make informed decisions in survival scenarios.
    Start: Survival Skills: Starting a Fire 
    Block 1: Text Block
    -	Title: Emergency Situation: Lost in the Woods
    -	Description: You find yourself lost in a dense forest as night approaches. The temperature is dropping, and you need to start a fire for warmth and to signal for help. Can you navigate through the challenges to successfully start a fire?
    Block 2: Media Block
    -	Title: Identifying Your Resources
    -	Media Type: 360-image
    -	Description: A 360-degree view of your surroundings in the forest. You can see various materials that could be useful for starting a fire.
    -	Overlay Tags:
    -	Text Tag: "Dry Leaves - Potential tinder."
    -	Text Tag: "Twigs and Branches - Small and medium-sized for kindling."
    -	Text Tag: "Large Logs - For sustaining the fire once started."
    Block 3: Branching Block (Simple Branching)
    -	Title: Choosing Your Tinder
    -	Proceed To Branch List:
    =>  Branch 3.1: Use Wet Leaves (Incorrect Path)
    =>  Branch 3.2: Use Dry Leaves (Correct Path)

    Branch 3.1: Use Wet Leaves (Incorrect Path)
    Block 3.1.1: Jump Block
    -	Title: Reevaluate Your Choices
    -	Proceed To Block: Block 3

    Branch 3.2: Use Dry Leaves (Correct Path)
    Block 3.2.1: Text Block
    -	Title: Gathering Tinder
    -	Description: You've chosen dry leaves, an excellent choice for tinder due to their quick ignition. Now, gather them cautiously to avoid dampening.
    Block 3.2.2: Media Block
    -	Title: Preparing the Fire Pit
    -	Media Type: Image
    -	Description: Instructions on clearing a space on the ground to create a fire pit, ensuring it's away from overhead and surrounding flammable materials.
    -	Overlay Tags:
    -	Text Tag: "Clearing Space - Ensure a safe area for the fire."
    -	Text Tag: "Safety First - Keep away from flammable materials."
    Block 3.2.3: Branching Block (Conditional Branching)
    -	Title: How to Arrange Your Tinder and Kindling?
    -	Timer: 30 seconds
    -	Question Text: Do you place the twigs and branches over the dry leaves or under them?
    -	Answers: "Over the dry leaves." / "Under the dry leaves."
    -	Proceed To Branch for each answer:
    =>  "Over the dry leaves.": Proceed to Branch 3.2.3.1: Over the dry leaves (Incorrect Path)
    =>  "Under the dry leaves.": Proceed to Branch 3.2.3.2: Under the dry leaves (Correct Path)
    
    Branch 3.2.3.1: Over the dry leaves (Incorrect Path)
    Block 3.2.3.1.1: Jump Block
    -	Title: Reevaluate Your Choices
    -	Proceed To Block: Block 3.2.3
    
    Branch 3.2.3.2: Under the dry leaves (Correct Path)
    Block 3.2.3.2.1: Text Block
    -	Title: Igniting the Fire
    -	Description: With the tinder and kindling correctly arranged, it's time to ignite your fire. You can use a flint, matches, or a lighter if you have one. Patience and persistence are key.
    Block 3.2.3.2.2: Goal Block
    -	Title: Fire Successfully Started! Congratulations! You've successfully started a fire and learned crucial survival skills. Remember, practice makes perfect, and these skills could be life-saving in real situations
    -	Score: 10.
                                                                                  
    Output:\n
{{
    "ScenarioType": "Escape Room Scenario",
    "LearningObjectives": [
        "Recognize and select appropriate materials in the wilderness that can be used as tinder, kindling, and fuel for starting a fire.",
        "Understand the importance of choosing the right tinder for ignition, distinguishing between materials that will ignite easily and those that won’t.",
        "Learn how to safely and effectively prepare a fire pit, ensuring it’s positioned away from flammable materials and structures.",
        "Master the correct way to arrange tinder, kindling, and larger logs to successfully start and maintain a fire.",
        "Emphasize the importance of fire safety in the wilderness to prevent wildfires and ensure personal safety.",
        "Apply critical thinking and problem-solving skills to navigate through challenges and make informed decisions in survival scenarios."
    ],
    "Start": "Survival Skills: Starting a Fire",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Emergency Situation: Lost in the Woods",
            "description": "You find yourself lost in a dense forest as night approaches. The temperature is dropping, and you need to start a fire for warmth and to signal for help. Can you navigate through the challenges to successfully start a fire?"
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "title": "Identifying Your Resources",
            "mediaType": "360-image",
            "description": "A 360-degree view of your surroundings in the forest. You can see various materials that could be useful for starting a fire.",
            "overlayTags": [
                {{
                    "textTag": "Dry Leaves - Potential tinder."
                }},
                {{
                    "textTag": "Twigs and Branches - Small and medium-sized for kindling."
                }},
                {{
                    "textTag": "Large Logs - For sustaining the fire once started."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choosing Your Tinder",
            "branches": {{
                "3.1": "Use Wet Leaves (Incorrect Path)",
                "3.2": "Use Dry Leaves (Correct Path)"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
               {{
"id": "3.1.1",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3"
        }}]}},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Text Block",
                    "title": "Gathering Tinder",
                    "description": "You've chosen dry leaves, an excellent choice for tinder due to their quick ignition. Now, gather them cautiously to avoid dampening."
                }},
                {{
                    "id": "3.2.2",
                    "type": "Media Block",
                    "title": "Preparing the Fire Pit",
                    "mediaType": "Image",
                    "description": "Instructions on clearing a space on the ground to create a fire pit, ensuring it's away from overhead and surrounding flammable materials.",
                    "overlayTags": [
                        {{
                            "textTag": "Clearing Space - Ensure a safe area for the fire."
                        }},
                        {{
                            "textTag": "Safety First - Keep away from flammable materials."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "How to Arrange Your Tinder and Kindling?",
                    "timer": "30 seconds",
                    "questionText": "Do you place the twigs and branches over the dry leaves or under them?",
                    "proceedToBranchForEachAnswer": [
                        {{
                            "text": "Over the dry leaves.",
                            "proceedToBlock": "3.2.3.1"
                        }},
                        {{
                            "text": "Under the dry leaves.",
                            "proceedToBlock": "3.2.3.2"
                        }}
                    ]
                }}
            ]
        }},
        {{
            "id": "3.2.3.1",
            "blocks": [
               {{
"id": "3.2.3.1.1",
            "type": "Jump Block",
            "title": "Reevaluate Your Choices",
            "proceedToBlock": "3.2.3"
        }}]}},
        {{
            "id": "3.2.3.2",
            "blocks": [
                {{
                    "id": "3.2.3.2.1",
                    "type": "Text Block",
                    "title": "Igniting the Fire",
                    "description": "With the tinder and kindling correctly arranged, it's time to ignite your fire. You can use a flint, matches, or a lighter if you have one. Patience and persistence are key."
                }},
                {{
                    "id": "3.2.3.2.2",
                    "type": "Goal Block",
                    "title": "Fire Successfully Started! Congratulations! You've successfully started a fire and learned crucial survival skills. Remember, practice makes perfect, and these skills could be life-saving in real situations",
                    "score": 10
                }}
            ]
        }}
    ]
}}

    \n\nEND OF EXAMPLE\n\n Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.   
    \n\n{text}Output:""")

    GRAPHML_PROMPT_LINEAR = PromptTemplate(input_variables=['text'], template="""You are a JSON intelligence helping a human track knowledge by giving providing them with
    JSON having various blocks representing information about all
    relevant people, things, concepts, etc. and integrating them with your knowledge stored within your weights as well as that stored in the JSON format.
    \n\nEXAMPLE\n\n
    \nLINEAR SCENARIO:\n
    Scenario Type: Linear Scenario
    Learning Objectives: 
    -	Identify and understand the common and atypical symptoms of heart attacks, emphasizing the variability among different individuals.
    -	Execute immediate and appropriate first aid responses for someone experiencing a heart attack, including ensuring comfort and administering aspirin when appropriate.
    -	Apply the DRSABCD action plan effectively in heart attack emergencies to enhance patient survival chances before medical help arrives.
    -	Assess and respond correctly to scenario-based questions on heart attack symptoms and first aid, reinforcing knowledge application in real-world situations.
    Start: Introduction to First Aid for Heart Attacks
    Block 1: Text Block
    -	Title: Understanding Heart Attacks
    -	Description: A heart attack is a life-threatening medical emergency. Knowing the signs and immediate actions can save lives. This course will guide you through recognizing heart attack symptoms, administering first aid, and understanding the importance of immediate medical intervention.
    Block 2: Media Block
    -	Title: Recognizing Heart Attack Symptoms
    -	Media Type: Image
    -	Description: An infographic showing common and atypical signs of a heart attack. Symptoms can vary greatly among individuals and might include chest discomfort, shortness of breath, and more.
    -	Overlay Tags:
    -	Text Tag: "Chest Pain - Described as tightness, heaviness, or squeezing."
    -	Audio Tag: "Atypical Symptoms - Includes shortness of breath, nausea, and faintness."
    -	Video Tag: "Symptom Variability - Understanding how symptoms can differ among different populations."
    Block 3: Question Block 
    -	Question Text: Which of the following is NOT a common symptom of a heart attack?
    -	Answers: "Chest pain," "Shortness of breath," "Sudden dizziness," "Rapid hair growth."
    -	Correct Answer: "Rapid hair growth"
    -	Wrong Answer Message: "Incorrect. Remember, common symptoms include chest pain, shortness of breath, and sudden dizziness. Hair growth is unrelated to heart attacks."
    Block 4: Text Block
    -	Timer: 45 seconds
    -	Title: Immediate Actions During a Heart Attack
    -	Description: Quick and appropriate actions can be critical. Learn the steps to assist someone experiencing a heart attack, from ensuring their comfort to administering aspirin, and when to perform CPR.
    Block 5: Media Block
    -	Title: First Aid for Heart Attack
    -	Media Type: Video
    -	Description: A step-by-step guide video on what to do if someone is having a heart attack, including DRSABCD protocol, how to assist with medication, and ensuring the patient is in a comfortable position.
    -	Overlay Tags:
    -	Text Tag: "DRSABCD - A reminder of the steps to take in an emergency."
    -	Video Tag: "Administering Aspirin - How and when to give aspirin safely."
    -	Audio Tag: "Comforting the Patient - The importance of reassurance."
    Block 6: Question Block
    -	Question Text: If the patient is conscious and experiencing heart attack symptoms, what is one of the first actions you should take?
    -	Answers: "Give them water," "Encourage them to keep moving," "Help them to sit or lie down and rest," "Leave them to find help."
    -	Correct Answer: "Help them to sit or lie down and rest"
    -	Wrong Answer Message: "Incorrect. The first step is to help the patient rest in a comfortable position to reduce strain on the heart."
    Block 7: Goal Block 
    -	Title: Heart Attack First Aid Mastery
    -	Score: 10.

                                   
    Output:\n
{{
  "ScenarioType": "Linear Scenario",
  "LearningObjectives": [
    "Identify and understand the common and atypical symptoms of heart attacks, emphasizing the variability among different individuals.",
    "Execute immediate and appropriate first aid responses for someone experiencing a heart attack, including ensuring comfort and administering aspirin when appropriate.",
    "Apply the DRSABCD action plan effectively in heart attack emergencies to enhance patient survival chances before medical help arrives.",
    "Assess and respond correctly to scenario-based questions on heart attack symptoms and first aid, reinforcing knowledge application in real-world situations."
  ],
  "Start": "Introduction to First Aid for Heart Attacks",
  "Blocks": [
    {{
      "id": "1",
      "type": "Text Block",
      "title": "Understanding Heart Attacks",
      "description": "A heart attack is a life-threatening medical emergency. Knowing the signs and immediate actions can save lives. This course will guide you through recognizing heart attack symptoms, administering first aid, and understanding the importance of immediate medical intervention."
    }},
    {{
      "id": "2",
      "type": "Media Block",
      "title": "Recognizing Heart Attack Symptoms",
      "mediaType": "Image",
      "description": "An infographic showing common and atypical signs of a heart attack. Symptoms can vary greatly among individuals and might include chest discomfort, shortness of breath, and more.",
      "overlayTags": [
        {{
          "textTag": "Chest Pain - Described as tightness, heaviness, or squeezing."
        }},
        {{
          "audioTag": "Atypical Symptoms - Includes shortness of breath, nausea, and faintness."
        }},
        {{
          "videoTag": "Symptom Variability - Understanding how symptoms can differ among different populations."
        }}
      ]
    }},
    {{
      "id": "3",
      "type": "Question Block",
      "questionText": "Which of the following is NOT a common symptom of a heart attack?",
      "answers": [
        "Chest pain",
        "Shortness of breath",
        "Sudden dizziness",
        "Rapid hair growth"
      ],
      "correctAnswer": "Rapid hair growth",
      "wrongAnswerMessage": "Incorrect. Remember, common symptoms include chest pain, shortness of breath, and sudden dizziness. Hair growth is unrelated to heart attacks."
    }},
    {{
      "id": "4",
      "type": "Text Block",
      "title": "Immediate Actions During a Heart Attack",
      "description": "Quick and appropriate actions can be critical. Learn the steps to assist someone experiencing a heart attack, from ensuring their comfort to administering aspirin, and when to perform CPR."
    }},
    {{
      "id": "5",
      "type": "Media Block",
      "title": "First Aid for Heart Attack",
      "mediaType": "Video",
      "description": "A step-by-step guide video on what to do if someone is having a heart attack, including DRSABCD protocol, how to assist with medication, and ensuring the patient is in a comfortable position.",
      "overlayTags": [
        {{
          "textTag": "DRSABCD - A reminder of the steps to take in an emergency."
        }},
        {{
          "videoTag": "Administering Aspirin - How and when to give aspirin safely."
        }},
        {{
          "audioTag": "Comforting the Patient - The importance of reassurance."
        }}
      ]
    }},
    {{
      "id": "6",
      "type": "Question Block",
      "questionText": "If the patient is conscious and experiencing heart attack symptoms, what is one of the first actions you should take?",
      "answers": [
        "Give them water",
        "Encourage them to keep moving",
        "Help them to sit or lie down and rest",
        "Leave them to find help"
      ],
      "correctAnswer": "Help them to sit or lie down and rest",
      "wrongAnswerMessage": "Incorrect. The first step is to help the patient rest in a comfortable position to reduce strain on the heart."
    }},
    {{
      "id": "7",
      "type": "Goal Block",
      "title": "Heart Attack First Aid Mastery",
      "score": 10
    }}
  ]
}}
    \n\nEND OF EXAMPLE\n\n Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.    
    \n\n{text}Output:""")

    GRAPHML_PROMPT_SELF_EXPLORATORY = PromptTemplate(input_variables=['text'], template="""You are a JSON intelligence helping a human track knowledge by giving providing them with
    JSON having various blocks representing information about all
    relevant people, things, concepts, etc. and integrating them with your knowledge stored within your weights as well as that stored in the JSON format.
    \n\nEXAMPLE\n\n
    \nSelf-Exploratory Scenario:\n
Scenario Type: Self Exploratory Scenario
Learning Objectives: 
-	Grasp the principles of how wind turbines and solar panels generate electricity.
-	Identify the differences between wind and solar energy, including their mechanisms and applications.
-	Acknowledge how renewable energy reduces carbon emissions and combats climate change.
-	Discover advancements in renewable energy technologies, such as transparent and flexible solar panels.
-	Learn about the installation, maintenance, and efficiency of solar energy systems in homes and businesses.
-	Assess the impact of renewable energy on reducing global carbon footprint and promoting sustainability.
Start: Introduction to Renewable Energy 
Block 1: Text Block
-	Title: Welcome to Renewable Energy Exploration
-	Description: Discover the shift towards renewable energy to combat climate change. This journey explores different renewable sources, their workings, and their impacts on our planet.
Block 2: Media Block
-	Title: A Glimpse into Renewable Energy Sources
-	Media Type: 360-image
-	Description: An immersive 360-degree image capturing an expansive green field, dotted with the leading technologies in renewable energy: gleaming solar panels and majestic wind turbines stand as testaments to sustainable power generation.
-	Overlay Tags: 
-	Text Tag: "Solar Panels - Harnessing sunlight to produce clean energy."
-	Text Tag: "Wind Turbines - Converting wind into electrical power through innovation."
Block 3: Branching Block (Simple Branching)
-	Title: Choose Your Renewable Energy Path
-	Proceed To Branch List:
=>  Branch 3.1: Wind Energy Exploration
=>  Branch 3.2: Solar Energy Exploration

Branch 3.1: Wind Energy Exploration
Block 3.1.1: Media Block
-	Title: How Wind Turbines Work
-	Media Type: Image
-	Description: This image offers a deep dive into the anatomy of a wind turbine through a detailed cross-section animation, illuminating the intricate mechanics from rotor to generator.
-	Overlay Tags: 
-	Video Tag: "Turbine Mechanics - An animated insight into the components that capture wind."
-	Text Tag: "Energy Conversion - The journey from wind to electricity explained visually."
Block 3.1.2: Media Block
-	Title: Environmental Benefits of Wind Energy
-	Media Type: Image
-	Description: An enlightening infographic that lays bare the environmental advantages of wind energy, comparing the minimal CO2 emissions to the higher rates associated with fossil fuels, underscoring the clean, sustainable future wind power promises.
-	Overlay Tags: 
-	Image Tag: "Emission Reduction - Graphical depiction of CO2 savings with wind energy."
-	Text Tag: "Renewable Benefits - Highlighting the eco-positive impacts of adopting wind power."
Block 3.1.3: Branching Block Explore More
-	Title: Explore More About Renewable Energies?
-	Proceed To Branch List:
=>  Branch 3.1.3.1: Yes, Jump Block
=>  Branch 3.1.3.2: No, Quiz
                                                     
Branch 3.1.3.1: Yes, Jump Block
Block 3.1.3.1.1: Jump Block
-	Title: Yes
-	Proceed To Block: Block 3
                                                     
Branch 3.1.3.2: No, Quiz
Block 3.1.3.2.1: Question Block
-	Question Text: What part of the wind turbine captures wind energy?
-	Answers: Blades, Rotor
-	Correct Answer: Blades
-	Wrong Answer Message: The blades are the correct answer, as they capture and convert wind energy into mechanical power.
Block 3.1.3.2.2: Question Block
-	Question Text: True or False: Wind energy produces greenhouse gases during electricity generation.
-	Answers: True, False
-	Correct Answer: False
-	Wrong Answer Message: False is correct, wind energy is a clean source that doesn't emit greenhouse gases during electricity generation.
Block 3.1.3.2.3: Goal Block
-	Title: Wind Energy course knowledge achieved
-	Score: 10.
                                                     
Branch 3.2: Solar Energy Exploration
Block 3.2.1: Media Block
-	Title: Solar Panels at Work
-	Media Type: Video
-	Description: This video elucidates the marvel of the photovoltaic effect within solar panels, from sunlight capture to electricity generation, demystifying the science with every frame.
-	Overlay Tags: 
-	Image Tag: "Emission Reduction - Graphical depiction of CO2 savings with wind energy."
-	Text Tag: "Renewable Benefits - Highlighting the eco-positive impacts of adopting wind power."
Block 3.2.2: Media Block
-	Title: Solar Energy for Homes and Businesses
-	Media Type: Image
-	Description: This case study presents a solar-powered smart home, emblematic of modern sustainability, showcasing how residential and commercial spaces can thrive on solar energy, emphasizing efficiency and cost savings.
-	Overlay Tags: 
-	Image Tag: "Smart Home Energy - A virtual showcase of solar-powered living."
-	Text Tag: "Cost Savings - The financial benefits of solar energy for homes and businesses illuminated."
Block 3.2.3: Media Block
-	Title: Installing Solar Panels
-	Media Type: Video
-	Description: A comprehensive video guide walks you through the installation of rooftop solar panels, covering every step from tool selection to safety measures, ensuring an efficient setup for maximum energy capture.
-	Overlay Tags: 
-	Text Tag: "Maintenance Tips - Best practices to keep your solar panels performing at their peak."
-	Video Tag: "Installation Process - Step-by-step video instructions for mounting solar panels."
Block 3.2.4: Media Block
-	Title: Future Solar Innovations
-	Media Type: Image
-	Description: Dive into the future with visualizations of cutting-edge solar technologies, including transparent solar panels for windows and flexible solar panels for varied applications, spotlighting the endless possibilities of solar innovation.
-	Overlay Tags: 
-	Video Tag: "Installation Process - Step-by-step video instructions for mounting solar panels."
-	Text Tag: "Maintenance Tips - Best practices to keep your solar panels performing at their peak."
Block 3.2.5: Branching Block Explore More
-	Title: Ready to Explore More About Renewable Energies?
-	Proceed To Branch List:
=>  Branch 3.2.5.1: Yes, Jump Block
=>  Branch 3.2.5.2: No, Quiz
                                                     
Branch 3.2.5.1: Yes, Jump Block
Block 3.2.5.1.1: Jump Block
-	Title: Yes
-	Proceed To Block: Block 3
                                                     
Branch 3.2.5.2: No, Quiz
Block 3.2.5.2.1: Question Block
-	Question Text: Solar panels are most efficient in which type of climate?
-	Answers: Sunny and cool, Hot and humid
-	Correct Answer: Sunny and cool
-	Wrong Answer Message: Solar panels perform best in sunny and cool climates, maximizing efficiency.
Block 3.2.5.2.2: Question Block	
-	Question Text: True or False: Solar panels cannot produce electricity on cloudy days.
-	Answers: True, False
-	Correct Answer: False
-	Wrong Answer Message: False is correct. Solar panels can still generate electricity on cloudy days, though at reduced efficiency.
Block 3.2.5.2.3: Goal Block
-	Title: Solar Energy course knowledge achieved
-	Score: 10.

    
    Output:\n
{{
    "ScenarioType": "Self Exploratory Scenario",
    "LearningObjectives": [
        "Grasp the principles of how wind turbines and solar panels generate electricity.",
        "Identify the differences between wind and solar energy, including their mechanisms and applications.",
        "Acknowledge how renewable energy reduces carbon emissions and combats climate change.",
        "Discover advancements in renewable energy technologies, such as transparent and flexible solar panels.",
        "Learn about the installation, maintenance, and efficiency of solar energy systems in homes and businesses.",
        "Assess the impact of renewable energy on reducing global carbon footprint and promoting sustainability."
    ],
    "Start": "Introduction to Renewable Energy",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Welcome to Renewable Energy Exploration",
            "description": "Discover the shift towards renewable energy to combat climate change. This journey explores different renewable sources, their workings, and their impacts on our planet."
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "title": "A Glimpse into Renewable Energy Sources",
            "mediaType": "360-image",
            "description": "An immersive 360-degree image capturing an expansive green field, dotted with the leading technologies in renewable energy: gleaming solar panels and majestic wind turbines stand as testaments to sustainable power generation.",
            "overlayTags": [
                {{
                    "textTag": "Solar Panels - Harnessing sunlight to produce clean energy."
                }},
                {{
                    "textTag": "Wind Turbines - Converting wind into electrical power through innovation."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Renewable Energy Path",
            "branches": {{
                "3.1": "Wind Energy Exploration",
                "3.2": "Solar Energy Exploration"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
                {{
                    "id": "3.1.1",
                    "type": "Media Block",
                    "title": "How Wind Turbines Work",
                    "mediaType": "Image",
                    "description": "This image offers a deep dive into the anatomy of a wind turbine through a detailed cross-section animation, illuminating the intricate mechanics from rotor to generator.",
                    "overlayTags": [
                        {{
                            "videoTag": "Turbine Mechanics - An animated insight into the components that capture wind."
                        }},
                        {{
                            "textTag": "Energy Conversion - The journey from wind to electricity explained visually."
                        }}
                    ]
                }},
                {{
                    "id": "3.1.2",
                    "type": "Media Block",
                    "title": "Environmental Benefits of Wind Energy",
                    "mediaType": "Image",
                    "description": "An enlightening infographic that lays bare the environmental advantages of wind energy, comparing the minimal CO2 emissions to the higher rates associated with fossil fuels, underscoring the clean, sustainable future wind power promises.",
                    "overlayTags": [
                        {{
                            "imageTag": "Emission Reduction - Graphical depiction of CO2 savings with wind energy."
                        }},
                        {{
                            "textTag": "Renewable Benefits - Highlighting the eco-positive impacts of adopting wind power."
                        }}
                    ]
                }},
                {{
                    "id": "3.1.3",
                    "type": "Branching Block Explore More",
                    "title": "Explore More About Renewable Energies?",
                    "branches": {{
                        "3.1.3.1": "Yes",
                        "3.1.3.2": "No"
                    }}
                }}
            ]
        }},
        {{
            "id": "3.1.3.1",
            "blocks": [
                {{
                    "id": "3.1.3.1.1",
                    "type": "Jump Block",
                    "title": "Yes",
                    "proceedToBlock": "3"
                }}
            ]
        }},
        {{
            "id": "3.1.3.2",
            "blocks": [
                {{
                    "id": "3.1.3.2.1",
                    "type": "Question Block",
                    "questionText": "What part of the wind turbine captures wind energy?",
                    "answers": [
                        "Blades",
                        "Rotor"
                    ],
                    "correctAnswer": "Blades",
                    "wrongAnswerMessage": "The blades are the correct answer, as they capture and convert wind energy into mechanical power."
                }},
                {{
                    "id": "3.1.3.2.2",
                    "type": "Question Block",
                    "questionText": "True or False: Wind energy produces greenhouse gases during electricity generation.",
                    "answers": [
                        "True",
                        "False"
                    ],
                    "correctAnswer": "False",
                    "wrongAnswerMessage": "False is correct, wind energy is a clean source that doesn't emit greenhouse gases during electricity generation."
                }},
                {{
                    "id": "3.1.3.2.3",
                    "type": "Goal Block",
                    "title": "Wind Energy course knowledge achieved",
                    "score": 10
                }}
            ]
        }},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Media Block",
                    "title": "Solar Panels at Work",
                    "mediaType": "Video",
                    "description": "This video elucidates the marvel of the photovoltaic effect within solar panels, from sunlight capture to electricity generation, demystifying the science with every frame.",
                    "overlayTags": [
                        {{
                            "imageTag": "Photovoltaic Cells - Converting sunlight into electrical energy."
                        }},
                        {{
                            "textTag": "Solar Efficiency - Exploring how solar panels maximize sunlight capture."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.2",
                    "type": "Media Block",
                    "title": "Solar Energy for Homes and Businesses",
                    "mediaType": "Image",
                    "description": "This case study presents a solar-powered smart home, emblematic of modern sustainability, showcasing how residential and commercial spaces can thrive on solar energy, emphasizing efficiency and cost savings.",
                    "overlayTags": [
                        {{
                            "imageTag": "Smart Home Energy - A virtual showcase of solar-powered living."
                        }},
                        {{
                            "textTag": "Cost Savings - The financial benefits of solar energy for homes and businesses illuminated."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.3",
                    "type": "Media Block",
                    "title": "Installing Solar Panels",
                    "mediaType": "Video",
                    "description": "A comprehensive video guide walks you through the installation of rooftop solar panels, covering every step from tool selection to safety measures, ensuring an efficient setup for maximum energy capture.",
                    "overlayTags": [
                        {{
                            "textTag": "Installation Process - Step-by-step video instructions for mounting solar panels."
                        }},
                        {{
                            "videoTag": "Maintenance Tips - Best practices to keep your solar panels performing at their peak."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.4",
                    "type": "Media Block",
                    "title": "Future Solar Innovations",
                    "mediaType": "Image",
                    "description": "Dive into the future with visualizations of cutting-edge solar technologies, including transparent solar panels for windows and flexible solar panels for varied applications, spotlighting the endless possibilities of solar innovation.",
                    "overlayTags": [
                        {{
                            "videoTag": "Next-Gen Solar - Exploring advancements in solar technology."
                        }},
                        {{
                            "textTag": "Innovative Applications - How new solar technologies can revolutionize energy generation."
                        }}
                    ]
                }},
                {{
                    "id": "3.2.5",
                    "type": "Branching Block Explore More",
                    "title": "Ready to Explore More About Renewable Energies?",
                    "branches": {{
                        "3.2.5.1": "Yes",
                        "3.2.5.2": "No"
                    }}
                }}
            ]
        }},
        {{
            "id": "3.2.5.1",
            "blocks": [
                {{
                    "id": "3.2.5.1.1",
                    "type": "Jump Block",
                    "title": "Yes",
                    "proceedToBlock": "3"
                }}
            ]
        }},
        {{
            "id": "3.2.5.2",
            "blocks": [
                {{
                    "id": "3.2.5.2.1",
                    "type": "Question Block",
                    "questionText": "Solar panels are most efficient in which type of climate?",
                    "answers": [
                        "Sunny and cool",
                        "Hot and humid"
                    ],
                    "correctAnswer": "Sunny and cool",
                    "wrongAnswerMessage": "Solar panels perform best in sunny and cool climates, maximizing efficiency."
                }},
                {{
                    "id": "3.2.5.2.2",
                    "type": "Question Block",
                    "questionText": "True or False: Solar panels cannot produce electricity on cloudy days.",
                    "answers": [
                        "True",
                        "False"
                    ],
                    "correctAnswer": "False",
                    "wrongAnswerMessage": "False is correct. Solar panels can still generate electricity on cloudy days, though at reduced efficiency."
                }},
                {{
                    "id": "3.2.5.2.3",
                    "type": "Goal Block",
                    "title": "Solar Energy course knowledge achieved",
                    "score": 10
                }}
            ]
        }}
    ]
}}
    \n\nEND OF EXAMPLE\n\n Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.  
    \n\n{text}Output:""")

    GRAPHML_PROMPT_SIMULATION = PromptTemplate(input_variables=['text'], template="""You are a JSON intelligence helping a human track knowledge by giving providing them with
    JSON having various blocks representing information about all
    relevant people, things, concepts, etc. and integrating them with your knowledge stored within your weights as well as that stored in the JSON format.
    \n\nEXAMPLE\n\n
    \nSIMULATION SCENARIO:\n
    Scenario Type: Simulation Scenario
    Learning Objectives: 
    - Recognize the importance of quick and informed decision-making during a fire emergency.
    - Identify fire safety protocols for avoidance of elevators and the use of staircases for evacuation.
    Start: Emergency Evacuation from a Building on Fire
    Block 1: Text Block
    -	Title: Emergency Alert
    -	Description: You are on the 5th floor of a 10-story office building when the fire alarm starts blaring. The loudspeakers announce a fire on the 7th floor. You must quickly decide how to exit the building.
    Block 2: Media Block
    -	Timer: 60 seconds
    -	Title: Choosing Your Exit
    -	Media Type: 360-degree image
    -	Description: You're presented with a crucial decision amidst the urgency of an evacuation on the 5th floor. This 360-degree view lays out your escape options: the risky main elevator, or the reliable staircase for a downward exit. Each choice carries its implications for safety and speed.
    -	Overlay Tags: 
    -	Text Tag: 'Main Elevator': An arrow pointing towards the elevator with a caption: "To the Ground Floor". 
    -	Text Tag: 'Staircase': An arrow pointing left with a caption: "To the Lower Floors". 
    Block 3: Branching Block (Simple Branching)
    -	Title: Choose Your Exit
    -	Timer: 45 seconds
    -	Proceed To Branch List:
    =>  Branch 3.1: Main Elevator
    =>  Branch 3.2: Staircase
    
    Branch 3.1: Main Elevator
    Block 3.1.1: Text Block
    -	Timer: 60 seconds
    -	Title: Elevator Failure
    -	Description: The elevator stops between the 4th and 5th floors due to the fire emergency systems. You are stuck until rescued by firefighters.
    Block 3.1.2: Goal Block
    -	Title: Stuck in the Elevator. Using the elevator during a fire resulted in failure to exit the building timely.
    -	Score: -10. 
    
    Branch 3.2: Staircase
    Block 3.2.1: Text Block
    -	Timer: 120 seconds
    -	Title: Descending the Stairs
    -	Description: You quickly head down the staircase, which is crowded and slow-moving due to the number of people trying to exit.
    Block 3.2.2: Branching Block (Conditional Branching)
    -	Title: Continue Down or Seek Another Exit?
    -	Timer: 45 seconds
    -	Question Text: The stairs are congested and progress is slow. Do you continue or look for another exit?
    -	Answers: "Continue down the stairs." / "Go back and use the emergency exit."
    -	Proceed To Branch for each answer:
    =>  "Continue down the stairs.": Proceed to Branch 3.2.2.1: Continue Downstairs
    =>  "Go back and use the emergency exit.": Proceed to Branch 3.2.2.2: Emergency Exit
    
    Branch 3.2.2.1: Continue Downstairs
    Block 3.2.2.1.1: Text Block
    -	Timer: 90 seconds
    -	Title: Safe, But Slow Exit
    -	Description: You eventually reach the ground floor, but precious time was lost, and the situation could have worsened, especially, a high risk of stampede is there.
    Block 3.2.2.1.2: Goal Block
    -	Title: Evacuated via Stairs. You safely exited the building, but with a time penalty for not choosing the fastest route.
    -	Score: 5 points.
    
    Branch 3.2.2.2: Emergency Exit
    Block 3.2.2.2.1: Text Block
    -	Timer: 60 seconds
    -	Title: Emergency Exit to Safety
    -	Description: You use the emergency exit and quickly descend the fire escape, reaching the ground safely and swiftly.
    Block 3.2.2.2.2: Goal Block
    -	Title: Successful and Swift Evacuation. You chose the safest and fastest route to exit the building during the fire.
    -	Score: 20 points.    
    Output:\n
{{
    "ScenarioType": "Simulation Scenario",
    "LearningObjectives": [
        "Recognize the importance of quick and informed decision-making during a fire emergency.",
        "Identify fire safety protocols for avoidance of elevators and the use of staircases for evacuation."
    ],
    "Start": "Emergency Evacuation from a Building on Fire",
    "Blocks": [
        {{
            "id": "1",
            "type": "Text Block",
            "title": "Emergency Alert",
            "description": "You are on the 5th floor of a 10-story office building when the fire alarm starts blaring. The loudspeakers announce a fire on the 7th floor. You must quickly decide how to exit the building."
        }},
        {{
            "id": "2",
            "type": "Media Block",
            "timer": "60 seconds",
            "title": "Choosing Your Exit",
            "mediaType": "360-degree image",
            "description": "You're presented with a crucial decision amidst the urgency of an evacuation on the 5th floor. This 360-degree view lays out your escape options: the risky main elevator, or the reliable staircase for a downward exit. Each choice carries its implications for safety and speed.",
            "overlayTags": [
                {{
                    "textTag": "'Main Elevator': An arrow pointing towards the elevator with a caption: 'To the Ground Floor'."
                }},
                {{
                    "textTag": "'Staircase': An arrow pointing left with a caption: 'To the Lower Floors'."
                }}
            ]
        }},
        {{
            "id": "3",
            "type": "Branching Block (Simple Branching)",
            "title": "Choose Your Exit",
            "timer": "45 seconds",
            "branches": {{
                "3.1": "Main Elevator",
                "3.2": "Staircase"
            }}
        }},
        {{
            "id": "3.1",
            "blocks": [
                {{
                    "id": "3.1.1",
                    "type": "Text Block",
                    "timer": "60 seconds",
                    "title": "Elevator Failure",
                    "description": "The elevator stops between the 4th and 5th floors due to the fire emergency systems. You are stuck until rescued by firefighters."
                }},
                {{
                    "id": "3.1.2",
                    "type": "Goal Block",
                    "title": "Stuck in the Elevator. Using the elevator during a fire resulted in failure to exit the building timely.",
                    "score": -10
                }}
            ]
        }},
        {{
            "id": "3.2",
            "blocks": [
                {{
                    "id": "3.2.1",
                    "type": "Text Block",
                    "timer": "120 seconds",
                    "title": "Descending the Stairs",
                    "description": "You quickly head down the staircase, which is crowded and slow-moving due to the number of people trying to exit."
                }},
                {{
                    "id": "3.2.2",
                    "type": "Branching Block (Conditional Branching)",
                    "title": "Continue Down or Seek Another Exit?",
                    "timer": "45 seconds",
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
                }}
            ]
        }},
        {{
            "id": "3.2.2.1",
            "blocks": [
                {{
                    "id": "3.2.2.1.1",
                    "type": "Text Block",
                    "timer": "90 seconds",
                    "title": "Safe, But Slow Exit",
                    "description": "You eventually reach the ground floor, but precious time was lost, and the situation could have worsened, especially, a high risk of stampede is there."
                }},
                {{
                    "id": "3.2.2.1.2",
                    "type": "Goal Block",
                    "title": "Evacuated via Stairs. You safely exited the building, but with a time penalty for not choosing the fastest route.",
                    "score": 5
                }}
            ]
        }},
        {{
            "id": "3.2.2.2",
            "blocks": [
                {{
                    "id": "3.2.2.2.1",
                    "type": "Text Block",
                    "timer": "60 seconds",
                    "title": "Emergency Exit to Safety",
                    "description": "You use the emergency exit and quickly descend the fire escape, reaching the ground safely and swiftly."
                }},
                {{
                    "id": "3.2.2.2.2",
                    "type": "Goal Block",
                    "title": "Successful and Swift Evacuation. You chose the safest and fastest route to exit the building during the fire ",
                    "score": 20
                }}
            ]
        }}
    ]
}}
    \n\nEND OF EXAMPLE\n\n Please note that you absolutely should not give response anything else outside the JSON format since
    human will be using the generated code directly into the server side to run the JSON code.
    Moreover, it is absolutley mandatory and necessary for you to generate a complete JSON response such that the JSON generated from you must enclose all the parenthesis at the end of your response
    and all it's parameters are also closed in the required syntax rules of JSON and all the blocks be included in it since we want our JSON
    to be compilable.    
    \n\n{text}Output:""")

    ### SEMANTIC ROUTES LOGIC ###
    linear = Route(
    name="linear",
    utterances=[
        f"linear scenario is mentioned in following= {bot_last_reply}",
    ],
    )
    escaperoom = Route(
        name="escape room",
        utterances=[
            f"escape room scenario is mentioned in following= {bot_last_reply}",
        ],
    )
    simulation = Route(
        name="simulation",
        utterances=[
            f"simulation scenario is mentioned in following= {bot_last_reply}",
        ],
    )
    selfexploratory = Route(
        name="self exploratory",
        utterances=[
            f"self exploratory scenario is mentioned in following= {bot_last_reply}",
        ],
    )
    routes = [linear, escaperoom, simulation, selfexploratory]
    encoder = OpenAIEncoder()
    rl = RouteLayer(encoder=encoder, routes=routes)
    x = rl(bot_last_reply)
    print("GraphML of NAME",x.name)
    ############################

    # llmsx = ChatOpenAI(model="gpt-3.5-turbo-16k-0613", temperature=0, streaming=True, callbacks=[StreamingStdOutCallbackHandler()])

    if x.name == 'escaperoom':
        graphml_chain = LLMChain(llm= llmsx, prompt=GRAPHML_PROMPT_ESCAPE_ROOM)
    elif x.name == 'linear':
        graphml_chain = LLMChain(llm= llmsx, prompt=GRAPHML_PROMPT_LINEAR)
    elif x.name == 'simulation':
        graphml_chain = LLMChain(llm= llmsx, prompt=GRAPHML_PROMPT_SIMULATION)
    else:
        graphml_chain = LLMChain(llm= llmsx, prompt=GRAPHML_PROMPT_SELF_EXPLORATORY)
    
    # output_graphml = graphml_chain.predict(text=bot_last_reply)

    return graphml_chain

def DRAW_GRAPH(output_graphml_generated_again, width,height):
    import networkx as nx
    import matplotlib.pyplot as plt
    import base64
    import io
    matplotlib.use('Agg')
    print(output_graphml_generated_again, width,height,"LCD SIDE")
    G = nx.read_graphml(output_graphml_generated_again)
    print("wow")
    plt.figure(figsize=(int(width),int(height)))
    options = {
        "font_size": 6,
        "linewidths": 3,
    }
    nx.draw_networkx(G, **options)
    ax = plt.gca()
    ax.margins(0.2)
    plt.axis('off')
    plt.plot()

    # Saving the plot to a buffer
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight')
    buffer.seek(0)
    
    # Converting the plot image to base64 for embedding in HTML
    plot_image = base64.b64encode(buffer.getvalue())
    plot_image_uri = f"data:image/png;base64,{plot_image.decode()}"
    
    return plot_image_uri

