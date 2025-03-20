
import streamlit as st
import google.generativeai as genai
import re
import json
import os
from datetime import datetime

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
            "tech_stack": []
        }
    if 'current_stage' not in st.session_state:
        st.session_state.current_stage = "greeting"
    if 'technical_questions' not in st.session_state:
        st.session_state.technical_questions = []
    if 'asked_questions' not in st.session_state:
        st.session_state.asked_questions = []

# Validate email format
def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

# Validate phone number format
def is_valid_phone(phone):
    # Basic validation - looks for a sequence of digits
    pattern = r'^\d{10,15}$'
    return re.match(pattern, phone) is not None

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
def generate_technical_questions(tech_stack, position):
    try:
        # Create a new model instance with the corrected model name
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Create a more detailed prompt that ensures questions cover different technologies
        prompt = f"""
        Generate 5 technical interview questions for a {position} candidate 
        who is proficient in the following technologies: {', '.join(tech_stack)}.
        
        Questions should:
        1. Be specific to the technologies mentioned - ensure you create at least one question for each major technology in the stack
        2. Range from basic to advanced
        3. Test both theoretical knowledge and practical application
        4. Be clear and concise
        
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
            st.session_state.current_stage = "tech_stack"
            return "Almost done with the basics! Now, please list your tech stack - all programming languages, frameworks, databases, and tools you're proficient with."
    
    elif st.session_state.current_stage == "tech_stack":
        # Process tech stack information
        tech_stack = [tech.strip() for tech in re.split(r'[,;]|\band\b', user_input) if tech.strip()]
        st.session_state.candidate_info["tech_stack"] = tech_stack
        
        # Generate technical questions
        st.session_state.current_stage = "generate_questions"
        
        # Use the updated function to generate questions
        st.session_state.technical_questions = generate_technical_questions(
            tech_stack, 
            st.session_state.candidate_info["desired_position"]
        )
        
        if not st.session_state.technical_questions:
            # Fallback if no questions were generated
            st.session_state.technical_questions = [
                {"question": f"1. Tell me about your experience with {tech_stack[0]}.", "answer": None},
                {"question": f"2. What projects have you worked on using {tech_stack[0]}?", "answer": None},
                {"question": f"3. How do you keep up with changes in {tech_stack[0]}?", "answer": None}
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

# Main app function
def main():
    st.set_page_config(page_title="TalentScout Hiring Assistant", page_icon="👨‍💻")
    
    # Initialize session variables
    initialize_session()
    
    # App header
    st.title("TalentScout Hiring Assistant")
    st.write("Welcome to the TalentScout technical screening interview.")
    
    # Reset button
    if st.sidebar.button("Reset Conversation"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        initialize_session()
        st.rerun()
    
    # Debug info in sidebar (can be removed in production)
    with st.sidebar.expander("Debug Info", expanded=False):
        st.write("Current Stage:", st.session_state.current_stage)
        st.write("Candidate Info:", st.session_state.candidate_info)
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
        
        I'll collect some basic information and ask a few technical questions to assess your experience with various technologies.
        
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