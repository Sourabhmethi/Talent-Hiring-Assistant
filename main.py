import streamlit as st
import google.generativeai as genai
import re
import json
import os
import io
from datetime import datetime
import PyPDF2
import docx
# import base64

# Set up the Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")  # Replace with your actual API key or use environment variable

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Updated model configuration - using the correct model name format
# The model name format might have changed in recent versions of the library
MODEL_NAME = "gemini-2.0-flash"  # Updated model name format

# Initialize session state variables
def initialize_session():
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'candidate_info' not in st.session_state:
        st.session_state.candidate_info = {
            "name": "",
            "email": "",
            "phone": "",
            "experience": "",
            "desired_position": "",
            "location": "",
            "tech_stack": [],
            "resume_text": "",  # New field for resume text
            "resume_filename": ""  # New field for resume filename
        }
    if 'current_stage' not in st.session_state:
        st.session_state.current_stage = "greeting"
    if 'technical_questions' not in st.session_state:
        st.session_state.technical_questions = []
    if 'asked_questions' not in st.session_state:
        st.session_state.asked_questions = []
    if 'resume_uploaded' not in st.session_state:
        st.session_state.resume_uploaded = False

# Validate email format
def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

# Validate phone number format
def is_valid_phone(phone):
    # Basic validation - looks for a sequence of digits
    pattern = r'^\d{10,15}$'
    return re.match(pattern, phone) is not None

# Extract text from PDF
def extract_text_from_pdf(file):
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return ""

# Extract text from DOCX
def extract_text_from_docx(file):
    try:
        doc = docx.Document(file)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    except Exception as e:
        st.error(f"Error extracting text from DOCX: {str(e)}")
        return ""

# Extract text from resume file
def extract_resume_text(uploaded_file):
    text = ""
    if uploaded_file is not None:
        # Create a copy of the file in memory
        bytes_data = uploaded_file.getvalue()
        
        # Determine file type and extract text
        file_type = uploaded_file.type
        file_name = uploaded_file.name
        
        if file_type == "application/pdf":
            text = extract_text_from_pdf(io.BytesIO(bytes_data))
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text = extract_text_from_docx(io.BytesIO(bytes_data))
        elif file_type == "text/plain":
            text = bytes_data.decode("utf-8")
        else:
            st.error(f"Unsupported file type: {file_type}. Please upload a PDF, DOCX, or TXT file.")
            
        # Save file info
        st.session_state.candidate_info["resume_filename"] = file_name
    
    return text

# Analyze resume using Gemini API
def analyze_resume(resume_text):
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        
        prompt = f"""
        Analyze the following resume text and extract key information:
        
        {resume_text}
        
        Please extract and format the following information:
        1. Name
        2. Email
        3. Phone number
        4. Total years of experience
        5. Most recent position/title
        6. Current/most recent location
        7. Technical skills and technologies (as a comma-separated list)
        
        Format your response as a JSON object with these keys: name, email, phone, experience, position, location, tech_stack
        Only return the JSON object, nothing else.
        """
        
        generation_config = {
            "temperature": 0.1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # Try to parse the response as JSON
        try:
            # First clean up the response to ensure it's valid JSON
            json_text = response.text.strip()
            # Remove markdown code blocks if present
            if json_text.startswith("```json"):
                json_text = json_text.replace("```json", "").replace("```", "").strip()
            elif json_text.startswith("```"):
                json_text = json_text.replace("```", "").strip()
                
            resume_data = json.loads(json_text)
            return resume_data
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error analyzing resume: {str(e)}")
        return None

# Save candidate data to file
def save_candidate_data():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"candidate_{timestamp}.json"
    
    # Create data directory if it doesn't exist
    if not os.path.exists("data"):
        os.makedirs("data")
    
    # Save the data
    with open(f"data/{filename}", "w") as f:
        json.dump({
            "candidate_info": st.session_state.candidate_info,
            "conversation_history": st.session_state.conversation_history,
            "technical_questions": st.session_state.technical_questions,
            "answers": [q for q in st.session_state.asked_questions if "answer" in q]
        }, f, indent=4)
    
    return filename

# Create system prompt for the chatbot
def get_system_prompt(stage):
    base_prompt = """You are the Hiring Assistant chatbot for TalentScout, a recruitment agency specializing in technology placements. 
    Your purpose is to screen candidates by gathering information and asking technical questions.
    Be professional, friendly, and concise in your responses.
    Do not disclose that you are an AI unless explicitly asked.
    """
    
    if stage == "greeting":
        return base_prompt + """
        Your task now is to greet the candidate and explain that you'll be collecting some information 
        for their application. Ask for their name first.
        """
    elif stage == "collecting_info":
        return base_prompt + f"""
        You are currently collecting candidate information.
        Current candidate info: {st.session_state.candidate_info}
        If any field is empty, politely ask for that information.
        Collect information in this order: name, email, phone, experience (in years), desired position, current location.
        Once you have all this information, ask the candidate about their tech stack (programming languages, frameworks, databases, tools).
        """
    elif stage == "tech_stack":
        return base_prompt + f"""
        You have collected the basic candidate information: {st.session_state.candidate_info}
        Now focus on understanding their tech stack in detail. Ask them to list all programming languages, 
        frameworks, databases, and tools they are proficient in. Encourage them to be specific.
        """
    elif stage == "resume_upload":
        return base_prompt + f"""
        You have collected the candidate's basic information.
        Now ask them to upload their resume for a more detailed assessment.
        Explain that they can upload a PDF, DOCX, or TXT file using the file uploader in the sidebar.
        """
    elif stage == "generate_questions":
        return base_prompt + f"""
        Based on the candidate's tech stack: {st.session_state.candidate_info['tech_stack']}, 
        generate 3-5 relevant technical questions to assess their proficiency.
        Format each question with a clear question number.
        Make sure to create questions for different technologies in their stack.
        Questions should range from basic to advanced to gauge their depth of knowledge.
        """
    elif stage == "ask_questions":
        return base_prompt + f"""
        You are now interviewing the candidate.
        Ask one technical question at a time from the list you've generated.
        After they answer, provide brief feedback or acknowledgment, then ask the next question.
        """
    elif stage == "conclusion":
        return base_prompt + f"""
        You have completed collecting information and asking technical questions.
        Thank the candidate for their time and inform them that their application has been recorded.
        Let them know that a TalentScout recruiter will contact them soon for the next steps.
        If they have any questions about the process, offer to answer them.
        """
    else:
        return base_prompt

# Generate technical questions using the Gemini API
def generate_technical_questions(tech_stack, position, resume_text=""):
    try:
        # Create a new model instance with the corrected model name
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Create a more detailed prompt that ensures questions cover different technologies
        prompt = f"""
        Generate 5 technical interview questions for a {position} candidate 
        who is proficient in the following technologies: {', '.join(tech_stack)}.
        
        Additional resume information:
        {resume_text[:5000] if resume_text else "Not provided"}
        
        Questions should:
        1. Be specific to the technologies mentioned - ensure you create at least one question for each major technology in the stack
        2. Range from basic to advanced
        3. Test both theoretical knowledge and practical application
        4. Be clear and concise
        5. If the resume is provided, tailor some questions to their specific experience
        
        Make sure to distribute questions across different technologies in the tech stack.
        Format the output as a numbered list of questions only, without any introductions or explanations.
        """
        
        # Generate content with safety settings
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
        
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Extract and format questions
        questions_text = response.text
        questions = []
        for line in questions_text.strip().split('\n'):
            if re.match(r'^\d+\.', line.strip()):
                questions.append({"question": line.strip(), "answer": None})
        
        return questions
    
    except Exception as e:
        # Fallback to more diverse questions if the API fails
        print(f"Error generating questions: {str(e)}")
        fallback_questions = []
        
        # Generate at least one question for each technology in the stack
        for i, tech in enumerate(tech_stack[:min(5, len(tech_stack))]):
            fallback_questions.append(
                {"question": f"{i+1}. What is your experience level with {tech}?", "answer": None}
            )
        
        # If we have fewer than 3 questions, add some general ones
        if len(fallback_questions) < 3:
            fallback_questions.append(
                {"question": f"{len(fallback_questions)+1}. Describe a challenging project you've worked on using any of these technologies.", "answer": None}
            )
            fallback_questions.append(
                {"question": f"{len(fallback_questions)+1}. How do you stay updated with the latest developments in your tech stack?", "answer": None}
            )
        
        return fallback_questions

# Process user input based on the current stage
def process_user_input(user_input):
    # Check for exit keywords
    exit_keywords = ["quit", "exit", "bye", "goodbye", "end interview", "stop"]
    if any(keyword in user_input.lower() for keyword in exit_keywords):
        st.session_state.current_stage = "conclusion"
        return "I understand you'd like to end our conversation. "
    
    # Process based on current stage
    if st.session_state.current_stage == "greeting":
        # Extract name from the response
        st.session_state.candidate_info["name"] = user_input.strip()
        st.session_state.current_stage = "collecting_info"
        return f"Nice to meet you, {st.session_state.candidate_info['name']}! Could you please provide your email address?"
    
    elif st.session_state.current_stage == "collecting_info":
        # Process each information field
        if not st.session_state.candidate_info["email"]:
            if is_valid_email(user_input.strip()):
                st.session_state.candidate_info["email"] = user_input.strip()
                return "Thank you! Now, could you please provide your phone number?"
            else:
                return "That doesn't look like a valid email address. Please enter a valid email (e.g., example@domain.com)."
        
        elif not st.session_state.candidate_info["phone"]:
            clean_phone = re.sub(r'[^0-9]', '', user_input)
            if is_valid_phone(clean_phone):
                st.session_state.candidate_info["phone"] = clean_phone
                return "Thanks! How many years of experience do you have in the technology field?"
            else:
                return "That doesn't look like a valid phone number. Please enter a valid phone number (digits only)."
        
        elif not st.session_state.candidate_info["experience"]:
            st.session_state.candidate_info["experience"] = user_input.strip()
            return "Great! What position are you applying for?"
        
        elif not st.session_state.candidate_info["desired_position"]:
            st.session_state.candidate_info["desired_position"] = user_input.strip()
            return "Thank you! What is your current location?"
        
        elif not st.session_state.candidate_info["location"]:
            st.session_state.candidate_info["location"] = user_input.strip()
            st.session_state.current_stage = "resume_upload"
            return "Thank you for providing your basic information. Could you please upload your resume using the file uploader in the sidebar? This will help us better understand your experience and skills. Supported formats are PDF, DOCX, and TXT."
    
    elif st.session_state.current_stage == "resume_upload":
        # After resume is processed, move to tech stack if response is received
        st.session_state.current_stage = "tech_stack"
        
        # Check if we already have tech stack info from the resume
        if st.session_state.resume_uploaded and st.session_state.candidate_info["tech_stack"]:
            tech_stack_str = ", ".join(st.session_state.candidate_info["tech_stack"])
            return f"Based on your resume, I see you have experience with: {tech_stack_str}. Could you please confirm or add any other technologies you're proficient with that may not be on your resume?"
        else:
            return "Now, please list your tech stack - all programming languages, frameworks, databases, and tools you're proficient with."
    
    elif st.session_state.current_stage == "tech_stack":
        # Process tech stack information
        if st.session_state.candidate_info["tech_stack"] and user_input.lower() in ["yes", "correct", "that's right", "that is correct", "confirmed", "looks good"]:
            # User confirmed the tech stack extracted from resume
            pass
        else:
            # User provided or updated tech stack
            tech_stack = [tech.strip() for tech in re.split(r'[,;]|\band\b', user_input) if tech.strip()]
            if st.session_state.candidate_info["tech_stack"]:
                # Merge with existing tech stack
                st.session_state.candidate_info["tech_stack"] = list(set(st.session_state.candidate_info["tech_stack"] + tech_stack))
            else:
                st.session_state.candidate_info["tech_stack"] = tech_stack
        
        # Generate technical questions
        st.session_state.current_stage = "generate_questions"
        
        # Use the updated function to generate questions
        st.session_state.technical_questions = generate_technical_questions(
            st.session_state.candidate_info["tech_stack"], 
            st.session_state.candidate_info["desired_position"],
            st.session_state.candidate_info["resume_text"]
        )
        
        if not st.session_state.technical_questions:
            # Fallback if no questions were generated
            st.session_state.technical_questions = [
                {"question": f"1. Tell me about your experience with {st.session_state.candidate_info['tech_stack'][0]}.", "answer": None},
                {"question": f"2. What projects have you worked on using {st.session_state.candidate_info['tech_stack'][0]}?", "answer": None},
                {"question": f"3. How do you keep up with changes in {st.session_state.candidate_info['tech_stack'][0]}?", "answer": None}
            ]
        
        st.session_state.current_stage = "ask_questions"
        
        return "Thank you for sharing your tech stack. I'll now ask you a few technical questions based on your experience. Here's the first question:\n\n" + st.session_state.technical_questions[0]["question"]
    
    elif st.session_state.current_stage == "ask_questions":
        # Process answers to technical questions
        if st.session_state.asked_questions:
            last_question = st.session_state.asked_questions[-1]
            last_question["answer"] = user_input
        else:
            # Add the first question to asked questions
            st.session_state.asked_questions.append({
                "question": st.session_state.technical_questions[0]["question"],
                "answer": user_input
            })
        
        # Check if we've asked all questions
        if len(st.session_state.asked_questions) >= len(st.session_state.technical_questions):
            st.session_state.current_stage = "conclusion"
            save_candidate_data()
            return "Thank you for answering all our technical questions! Your application has been recorded. A TalentScout recruiter will contact you soon to discuss the next steps. Do you have any questions about the process?"
        
        # Ask the next question
        next_question = st.session_state.technical_questions[len(st.session_state.asked_questions)]
        st.session_state.asked_questions.append({
            "question": next_question["question"],
            "answer": None
        })
        
        return f"Thank you for your answer. Let's move on to the next question:\n\n{next_question['question']}"
    
    elif st.session_state.current_stage == "conclusion":
        # Handle any final questions from the candidate
        try:
            # Use the Gemini API to generate a response
            model = genai.GenerativeModel(MODEL_NAME)
            
            prompt = f"""
            The candidate has asked: {user_input}
            
            You are concluding the interview process. Answer their question professionally and concisely.
            If they have questions about when they'll hear back, let them know a recruiter will review their 
            application and contact them within 3-5 business days.
            If they're asking about next steps, explain there might be additional technical interviews and a culture fit assessment.
            If they ask about something you can't answer, politely inform them that a recruiter will be able to provide more specific information.
            """
            
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            # Fallback response if the API call fails
            print(f"Error in conclusion stage: {str(e)}")
            return "Thank you for your question. A recruiter will review your application and contact you within 3-5 business days to discuss the next steps in the hiring process."
    
    # Fallback for unexpected states
    return "I'm sorry, I didn't understand. Could you please rephrase your response?"

# Handle resume upload and processing
def handle_resume_upload():
    if st.session_state.current_stage == "resume_upload" or not st.session_state.resume_uploaded:
        uploaded_file = st.sidebar.file_uploader("Upload your resume (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
        
        if uploaded_file is not None:
            # Process the resume
            with st.sidebar:
                with st.spinner("Processing resume..."):
                    # Extract text from resume
                    resume_text = extract_resume_text(uploaded_file)
                    st.session_state.candidate_info["resume_text"] = resume_text
                    
                    # Analyze resume with Gemini
                    if resume_text:
                        resume_data = analyze_resume(resume_text)
                        
                        if resume_data:
                            # Update session state with resume data
                            st.write("✅ Resume processed successfully!")
                            
                            # Show extracted information
                            with st.expander("Resume Information", expanded=False):
                                st.json(resume_data)
                            
                            # Pre-fill candidate info from resume if fields are empty
                            if not st.session_state.candidate_info["name"] and "name" in resume_data:
                                st.session_state.candidate_info["name"] = resume_data["name"]
                            if not st.session_state.candidate_info["email"] and "email" in resume_data:
                                st.session_state.candidate_info["email"] = resume_data["email"]
                            if not st.session_state.candidate_info["phone"] and "phone" in resume_data:
                                st.session_state.candidate_info["phone"] = resume_data["phone"]
                            if not st.session_state.candidate_info["experience"] and "experience" in resume_data:
                                st.session_state.candidate_info["experience"] = resume_data["experience"]
                            if not st.session_state.candidate_info["desired_position"] and "position" in resume_data:
                                st.session_state.candidate_info["desired_position"] = resume_data["position"]
                            if not st.session_state.candidate_info["location"] and "location" in resume_data:
                                st.session_state.candidate_info["location"] = resume_data["location"]
                            
                            # Extract tech stack
                            if "tech_stack" in resume_data and resume_data["tech_stack"]:
                                if isinstance(resume_data["tech_stack"], list):
                                    tech_stack = resume_data["tech_stack"]
                                else:
                                    # Split string into list
                                    tech_stack = [tech.strip() for tech in re.split(r'[,;]|\band\b', resume_data["tech_stack"]) if tech.strip()]
                                
                                st.session_state.candidate_info["tech_stack"] = tech_stack
                        else:
                            st.warning("Resume was processed but automatic information extraction failed. You'll need to provide your information manually.")
                    
                    # Mark as uploaded
                    st.session_state.resume_uploaded = True
                    
                    # Create a download link for the processed resume text
                    if resume_text:
                        st.download_button(
                            label="Download Extracted Text",
                            data=resume_text,
                            file_name="extracted_resume.txt",
                            mime="text/plain"
                        )

# Main app function
def main():
    st.set_page_config(page_title="TalentScout Hiring Assistant", page_icon="👨‍💻")
    
    # Initialize session variables
    initialize_session()
    
    # App header
    st.title("TalentScout Hiring Assistant")
    st.write("Welcome to the TalentScout technical screening interview.")
    
    # Sidebar
    st.sidebar.title("Candidate Tools")
    
    # Reset button
    if st.sidebar.button("Reset Conversation"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        initialize_session()
        st.rerun()
    
    # Resume uploader in sidebar
    handle_resume_upload()
    
    # Debug info in sidebar (can be removed in production)
    with st.sidebar.expander("Debug Info", expanded=False):
        st.write("Current Stage:", st.session_state.current_stage)
        st.write("Candidate Info:", {k: v for k, v in st.session_state.candidate_info.items() if k != "resume_text"})
        st.write("Resume Uploaded:", st.session_state.resume_uploaded)
        st.write("Technical Questions:", st.session_state.technical_questions)
        st.write("Asked Questions:", st.session_state.asked_questions)
    
    # Display conversation history
    for message in st.session_state.conversation_history:
        role = "assistant" if message["role"] == "assistant" else "user"
        with st.chat_message(role):
            st.write(message["content"])
    
    # Initial greeting message if conversation is just starting
    if len(st.session_state.conversation_history) == 0:
        greeting = """
        Hello! I'm the TalentScout Hiring Assistant. I'll be conducting your initial screening interview.
        
        I'll collect some basic information, ask you to upload your resume, and then ask a few technical questions to assess your experience with various technologies.
        
        Let's start with your name. What is your full name?
        """
        with st.chat_message("assistant"):
            st.write(greeting)
        st.session_state.conversation_history.append({"role": "assistant", "content": greeting})
    
    # Get user input
    user_input = st.chat_input("Type your response here...")
    
    # Process user input
    if user_input:
        # Display user message
        with st.chat_message("user"):
            st.write(user_input)
        
        # Add to conversation history
        st.session_state.conversation_history.append({"role": "user", "content": user_input})
        
        # Process the input based on current stage
        response = process_user_input(user_input)
        
        # Display assistant response
        with st.chat_message("assistant"):
            st.write(response)
        
        # Add to conversation history
        st.session_state.conversation_history.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
