import json
import os
import re
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List,Dict,Any
from bson import ObjectId
import jwt
from openai import OpenAI
import fitz
from fastapi import File, UploadFile,Form
from fastapi.middleware.cors import CORSMiddleware

from .db import users_collection, financial_data_collection, chat_collection

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Initialize OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)
# ------------------------
# Pydantic Models
# ------------------------

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    age: Optional[str] = None
    goal: Optional[str] = None
    risk_tolerance: Optional[str] = None
    work_type : Optional[str] = None
class ProfileUpdateRequest(BaseModel):
    age: Optional[str] = None
    goal: Optional[str] = None
    risk_tolerance: Optional[str] = None

# Pydantic Response Model
class ProfileResponse(BaseModel):
    message: str
    income_mode: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    updated_profile: Optional[Dict[str, Any]] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None

class ChatMessage(BaseModel):
    user_id: str
    message: str
    thread_id: Optional[str] = None
class FinancialData(BaseModel):
    user_id: str
    income: float
    expenses: float

class TokenRefreshRequest(BaseModel):
    refresh_token: str

# class QuizRequest(BaseModel):
#     user_id: str
#     goals: str
#     risk_tolerance: str

class ITRResponse(BaseModel):
    message: str
    income_mode: str
    extracted_data: Dict[str, Any]
# ------------------------
# JWT Utility Functions
# ------------------------

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

def create_access_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def create_refresh_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

    
def parse_itr(text: str) -> Dict[str, Any]:
    """
    Parses the extracted ITR text and returns structured key-value data.
    """
    parsed_data = {}

    # Extract personal details
    name_match = re.search(r"Name:\s*([\w ]+)", text)
    parsed_data["name"] = name_match.group(1).strip() if name_match else None
    parsed_data["pan"] = re.search(r"PAN:\s*([\w\d]+)", text).group(1) if re.search(r"PAN:\s*([\w\d]+)", text) else None
    parsed_data["address"] = re.search(r"Address:\s*(.+)", text).group(1) if re.search(r"Address:\s*(.+)", text) else None
    parsed_data["contact"] = re.search(r"Contact:\s*([\d]+)", text).group(1) if re.search(r"Contact:\s*([\d]+)", text) else None

    # Extract income details
    salary_match = re.search(r"Salary Income:\s*Rs\.([\d,]+)", text)
    business_match = re.search(r"Business Turnover:\s*Rs\.([\d,]+)", text)
    
    parsed_data["salary_income"] = salary_match.group(1).replace(",", "") if salary_match else None
    parsed_data["business_turnover"] = business_match.group(1).replace(",", "") if business_match else None

    # Determine income mode
    if parsed_data["salary_income"]:
        parsed_data["income_mode"] = "salary"
    elif parsed_data["business_turnover"]:
        parsed_data["income_mode"] = "business"
    else:
        parsed_data["income_mode"] = "unknown"

    # Extract deductions
    parsed_data["deduction_80C"] = re.search(r"80C.*?:\s*Rs\.([\d,]+)", text).group(1).replace(",", "") if re.search(r"80C.*?:\s*Rs\.([\d,]+)", text) else None
    parsed_data["deduction_80D"] = re.search(r"80D.*?:\s*Rs\.([\d,]+)", text).group(1).replace(",", "") if re.search(r"80D.*?:\s*Rs\.([\d,]+)", text) else None

    # Extract tax computation details
    parsed_data["taxable_income"] = re.search(r"Taxable Income:\s*Rs\.([\d,]+)", text).group(1).replace(",", "") if re.search(r"Taxable Income:\s*Rs\.([\d,]+)", text) else None
    parsed_data["total_tax_payable"] = re.search(r"Total Tax Payable:\s*Rs\.([\d,]+)", text).group(1).replace(",", "") if re.search(r"Total Tax Payable:\s*Rs\.([\d,]+)", text) else None
    parsed_data["tds_deducted"] = re.search(r"TDS Deducted:\s*Rs\.([\d,]+)", text).group(1).replace(",", "") if re.search(r"TDS Deducted:\s*Rs\.([\d,]+)", text) else None
    parsed_data["refund_due"] = re.search(r"Refund Due:\s*Rs\.([\d,]+)", text).group(1).replace(",", "") if re.search(r"Refund Due:\s*Rs\.([\d,]+)", text) else None

    return parsed_data

# ------------------------
# JWT Dependency
# ------------------------

auth_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# ------------------------
# Helper Function
# ------------------------
def convert_object_id(document: dict) -> dict:
    document["_id"] = str(document["_id"])
    return document

# ------------------------
# Root Eparsed_data["name"] = re.search(r"Name:\s*([\w\s]+)", text).group(1) if re.search(r"Name:\s*([\w\s]+)", text) else Nonendpoint
# ------------------------
@app.get("/")
async def root():
    return {"message": "Welcome to the FinTech AI Financial Inclusion API"}

# ------------------------
# User Management Endpoints
# ------------------------
@app.get("/users", response_model=List[dict])
async def get_users(current_user: dict = Depends(get_current_user)):
    users = [convert_object_id(user) for user in users_collection.find({})]
    return users

@app.post("/users/register")
async def register_user(
    username: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    age: Optional[str] = Form(None),
    goal: Optional[str] = Form(None),
    risk_tolerance: Optional[str] = Form(None),
    work_type: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    try:
        if users_collection.find_one({"email": email}):
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user data dictionary
        new_user = {
            "username": username,
            "email": email,
            "password": password,
            "age": age,
            "goal": goal,
            "risk_tolerance": risk_tolerance,
            "work_type": work_type
        }
        
        # Process ITR file if uploaded
        if file:
            try:
                pdf_bytes = await file.read()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                extracted_text = "\n".join([page.get_text("text") for page in doc])

                extracted_data = parse_itr(extracted_text)
                income_mode = extracted_data.get("income_mode", "unknown")

                # Add extracted ITR data to user data
                new_user.update(extracted_data)
                new_user["income_mode"] = income_mode

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error processing ITR: {str(e)}")
        
        # Insert user into database
        result = users_collection.insert_one(new_user)
        new_user["_id"] = str(result.inserted_id)
        user_id = new_user["_id"]
        user_data = {"user_id": user_id, "email": new_user["email"]}
        access_token = create_access_token(user_data)
        refresh_token = create_refresh_token(user_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering user: {str(e)}")
    
@app.post("/users/login")
async def login_user(user: UserLogin):
    try:
        db_user = users_collection.find_one({"email": user.email, "password": user.password})
        if not db_user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_data = {"user_id": str(db_user["_id"]), "email": db_user["email"]}
        access_token = create_access_token(user_data)
        refresh_token = create_refresh_token(user_data)
        return {"access_token": access_token, "refresh_token": refresh_token,"user_id":str(db_user["_id"])}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
@app.post("/token/refresh")
async def refresh_access_token(token_request: TokenRefreshRequest):
    try:
        payload = jwt.decode(token_request.refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_data = {"user_id": payload.get("user_id"), "email": payload.get("email")}
        new_access_token = create_access_token(user_data)
        return {"access_token": new_access_token, "token_type": "bearer"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@app.get("/users/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return convert_object_id(user)

@app.put("/users/{user_id}")
async def update_user(user_id: str, user_update: UserUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in user_update.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided for update")
    result = users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User updated successfully"}


@app.put("/user/profile", response_model=ProfileResponse)
async def update_profile(
    file: Optional[UploadFile] = File(None),
    age: Optional[str] = Form(None),
    goal: Optional[str] = Form(None),
    risk_tolerance: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Update user profile information OR upload an ITR file to extract financial details.
    This endpoint allows both operations in a single request.
    """
    user_id = current_user["_id"]
    update_data = {}
    extracted_data = None
    income_mode = None

    # Process ITR file if uploaded
    if file:
        try:
            pdf_bytes = await file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            extracted_text = "\n".join([page.get_text("text") for page in doc])

            extracted_data = parse_itr(extracted_text)
            income_mode = extracted_data.get("income_mode", "unknown")

            # Store extracted ITR data
            update_data.update(extracted_data)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing ITR: {str(e)}")

    # Process form fields
    if age:
        update_data["age"] = age
    if goal:
        update_data["goal"] = goal
    if risk_tolerance:
        update_data["risk_tolerance"] = risk_tolerance

    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided for update")
    
    # Update user profile in MongoDB
    users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})

    # Fetch updated user profile
    updated_user = users_collection.find_one({"_id": ObjectId(user_id)})

    return ProfileResponse(
        message="Profile updated successfully.",
        income_mode=income_mode,
        extracted_data=extracted_data,
        updated_profile=convert_object_id(updated_user)
    )

@app.post("/chat")
async def chat(chat_msg: ChatMessage, current_user: dict = Depends(get_current_user)):
    try:
        # Call the ChatGPT API using OpenAI's ChatCompletion endpoint
        user_id = current_user["_id"]
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
         
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": 
                """
                You are a virtual financial assistant. Provide general or data-driven advice on budgeting, investing, and debt management. You are not a certified professional—always include disclaimers and advise consultation with experts. If user data is provided, customize responses; otherwise, offer general guidance. Maintain a professional, concise, and approachable tone. Respect privacy. When unsure, clarify assumptions. Clearly distinguish fact from opinion, disclaim liability, and encourage users to verify information.

                ### **Response Format**
                Your response must always be in the following JSON format:
                {
                "text": "res",
                "chart_names": "highcharts obj"
                }

                - `"text"` must contain a **single plain-text paragraph without any formatting** (no bullet points, line breaks, bold text, or special characters).
                - `"text"` must be **concise and to the point**.
                - `"chart_names"` contains a Highcharts-compatible object **only when the response includes numerical data**.
                - If no chart is needed, set `"chart_names": null`.

                ### **Example of a Chart-Compatible Object**
                {
                "chart_names": {
                    "type": "bar",
                    "data": [
                    { "name": "Stocks", "value": 15 },
                    { "name": "Bonds", "value": 5 },
                    { "name": "Real Estate", "value": 10 },
                    { "name": "Commodities", "value": 8 },
                    { "name": "Cash", "value": 1 }
                    ],
                    "options": {
                    "xKey": "name",
                    "yKey": "value",
                    "title": "Asset Class Performance (% Return)"
                    }
                }
                }

                ### **Chart Type Explanation**
                - `"type"` defines the appropriate chart format:
                - `"bar"` → for comparisons (e.g., asset allocation, spending categories)
                - `"line"` → for trends (e.g., stock performance, savings growth)
                - `"pie"` → for proportion-based data (e.g., portfolio distribution)
                - `"scatter"` → for correlation analysis (e.g., risk vs. return)

                - `"data"` includes key-value pairs representing the dataset.
                - `"options"` specifies Highcharts-compatible keys like `"xKey"`, `"yKey"`, and `"title"`.

                ### **Key Constraints**
                - **No bullet points, line breaks, bold text, or special characters in `"text"`**. The response must be a **single, unformatted plain-text paragraph**.
                - **If the response contains numerical data, include a `"chart_names"` object** with an appropriate `"type"`.
                - **If no numerical data is present, set `"chart_names": null"`.

                ### **Correct Example of `text`**
                {
                "text": "Based on your income of 32,000 INR per month, you can allocate 20% (6,400 INR) for an emergency fund, 30% (9,600 INR) for SIP investments, 10% (3,200 INR) for retirement savings, 10% (3,200 INR) for medium-term goals, and 30% (9,600 INR) for living expenses and discretionary spending. Regularly review your strategy and consult a financial advisor to ensure alignment with your goals.",
                "chart_names": {
                    "type": "pie",
                    "data": [
                    { "name": "Emergency Fund", "value": 20 },
                    { "name": "SIP Investment", "value": 30 },
                    { "name": "Retirement Savings", "value": 10 },
                    { "name": "Short to Medium-Term Goals", "value": 10 },
                    { "name": "Living Expenses and Discretionary Spending", "value": 30 }
                    ],
                    "options": {
                    "xKey": "name",
                    "yKey": "value",
                    "title": "Income Allocation Strategy"
                    }
                }
                }

                """},
                {"role": "user", "content": chat_msg.message}
            ]
        )
        answer = response.choices[0].message.content
        answer_json = json.loads(answer)
        timestamp = datetime.utcnow()
        thread_id = None
        if chat_msg.thread_id:
            chat_thread = chat_collection.find_one({"_id": ObjectId(chat_msg.thread_id)})
            if chat_thread:
                # Update existing thread
                thread_id = chat_msg.thread_id
                chat_collection.update_one(
                    {"_id": ObjectId(thread_id)},
                    {"$push": {"messages": {
                        "role": "user",
                        "content": chat_msg.message,
                        "timestamp": timestamp
                    }}}
                )
                chat_collection.update_one(
                    {"_id": ObjectId(thread_id)},
                    {"$push": {"messages": {
                        "role": "assistant",
                        "content": answer_json,
                        "timestamp": timestamp
                    }}}
                )
        
        # If thread_id wasn't provided or wasn't found, create a new thread
        if not thread_id:
            result = chat_collection.insert_one({
                "user_id": str(user_id),
                "created_at": timestamp,
                "messages": [
                    {
                        "role": "user",
                        "content": chat_msg.message,
                        "timestamp": timestamp
                    },
                    {
                        "role": "assistant",
                        "content": answer_json,
                        "timestamp": timestamp
                    }
                ]
            })
            thread_id = str(result.inserted_id)
        
        # Return the answer and thread_id
        return {
            "response": answer_json,
            "thread_id": thread_id
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error parsing response from OpenAI")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

@app.post("/financial-data")
async def add_financial_data(data: FinancialData, current_user: dict = Depends(get_current_user)):
    result = financial_data_collection.insert_one(data.dict())
    return {"message": "Financial data added", "id": str(result.inserted_id)}

@app.get("/financial-recommendations/{user_id}")
async def get_financial_recommendations(user_id: str, current_user: dict = Depends(get_current_user)):
    data = financial_data_collection.find_one({"user_id": user_id})
    if not data:
        raise HTTPException(status_code=404, detail="Financial data not found for user")
    recommendation = "Save more" if data["income"] > data["expenses"] else "Cut down expenses"
    return {"recommendation": recommendation}

@app.get("/dashboard/{user_id}")
async def get_dashboard(user_id: str, current_user: dict = Depends(get_current_user)):
    data = financial_data_collection.find_one({"user_id": user_id})
    if not data:
        return {"message": "No financial data available for user", "dashboard": {}}
    dashboard = {
        "income": data["income"],
        "expenses": data["expenses"],
        "net": data["income"] - data["expenses"],
    }
    return {"dashboard": dashboard}


@app.post("/generate-quiz")
async def generate_quiz(
    current_user: dict = Depends(get_current_user)
):
    """
    Dynamically generate a 10-question quiz with 4 multiple-choice options each
    (A, B, C, D), focusing on increasing financial literacy. Exactly one option
    should be correct per question. The quiz is tailored to the user’s goals 
    and risk tolerance.
    """
    user_id = current_user["_id"]
    user  = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Incorporate user’s financial goals and risk tolerance into the prompt
    prompt = f"""
    The user's details are as follows:
    {user}

    Create a quiz with exactly 10 multiple-choice questions to help them 
    build financial literacy. Tailor questions to their stated goals and 
    risk-taking capacity where possible. Topics can include budgeting, 
    saving, investing, credit management, debt reduction, retirement planning, 
    and other relevant areas.

    Each question must have exactly four answer options: A, B, C, D.
    Exactly one option per question is correct; mark it as "is_correct": true.
    The other three must be "is_correct": false.

    Return ONLY valid JSON in the following format (no extra commentary):

    {{
      "quiz": [
        {{
          "question": "Question text",
          "options": [
            {{
              "option": "A: Option text",
              "is_correct": boolean
            }},
            {{
              "option": "B: Option text",
              "is_correct": boolean
            }},
            {{
              "option": "C: Option text",
              "is_correct": boolean
            }},
            {{
              "option": "D: Option text",
              "is_correct": boolean
            }}
          ]
        }},
        ... (9 more questions) ...
      ]
    }}
    """

    try:
        # Call GPT-4 to generate the quiz
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # or "gpt-4" if available
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an AI that generates multiple-choice quizzes in strict JSON format. "
                        "Do not include markdown or additional commentary outside the JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # GPT-4 returns text; parse as JSON
        content = response.choices[0].message.content.strip()
        quiz_data = json.loads(content)  # Attempt to parse the JSON

        # Optional: Validate the structure or question count if needed
        if "quiz" not in quiz_data or len(quiz_data["quiz"]) != 10:
            raise HTTPException(status_code=500, detail="Quiz structure invalid or not 10 questions.")

        return quiz_data

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="GPT-4 returned invalid JSON.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
