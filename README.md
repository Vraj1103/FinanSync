# TEAM ID : 05

# **FinTech AI Financial Inclusion - Backend**

A **FastAPI-based** application that leverages **AI** to provide financial inclusion services, including **personalized financial advice, document processing, and financial literacy tools**.

---

## **Features**

- **User Authentication & Management**: JWT-based authentication system with access and refresh tokens.
- **ITR Document Processing**: Extract and analyze financial data from **Income Tax Returns (ITRs)**.
- **AI Financial Assistant**: Chat with a specialized **financial advisor powered by GPT-4o**.
- **Financial Dashboard**: Track **income, expenses**, and get financial insights.
- **Financial Literacy Quiz**: **Dynamically generated quizzes** based on user profile.
- **Personalized Recommendations**: Get **tailored financial advice** based on your financial situation.

---

## **Tech Stack**

- **Backend Framework**: FastAPI
- **Database**: MongoDB
- **AI Integration**: OpenAI GPT-4o
- **Authentication**: JWT
- **PDF Processing**: PyMuPDF (fitz)
- **Cross-Origin Support**: Full CORS implementation

---

## **Installation & Setup**

### **Prerequisites**

- **Python 3.8+**
- **MongoDB instance**
- **OpenAI API key**

### **Steps**

```sh
# 1. Clone the repository
git clone https://github.com/your-repo/fintech-ai-api.git
cd fintech-ai-api

# 2. Set up a virtual environment
python -m venv venv
source venv/bin/activate   # On Windows, use: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file with your credentials
echo "JWT_SECRET=your_jwt_secret" >> .env
echo "OPENAI_API_KEY=your_openai_api_key" >> .env
echo "MONGODB_URI=your_mongodb_connection_string" >> .env

# 5. Start the server
uvicorn main:app --reload
```

## **API Endpoints**

### **Authentication**

#### Register a new user

```sh
POST /users/register
```

#### Login and get access token

```sh
POST /users/login
```

#### Refresh access token

```sh
POST /token/refresh
```

### **User Management**

#### List all users (admin only)

```sh
GET /users
```

#### Get user details

```sh
GET /users/{user_id}
```

#### Update user information

```sh
PUT /users/{user_id}
```

#### Update user profile with optional ITR file upload

```sh
PUT /user/profile
```

### **Financial Services**

#### Chat with AI financial assistant

```sh
POST /chat
```

#### Add financial data (income/expenses)

```sh
POST /financial-data
```

#### Get personalized financial recommendations

```sh
GET /financial-recommendations/{user_id}
```

#### View financial dashboard

```sh
GET /dashboard/{user_id}
```

#### Generate personalized financial literacy quiz

```sh
POST /generate-quiz
```
