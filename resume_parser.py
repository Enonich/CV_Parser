import os
import json
from dotenv import load_dotenv
from typing import List, Optional
from pydantic import BaseModel, Field
from llama_cloud_services import LlamaExtract

# Load environment variables and get API key
def get_llama_key():
    load_dotenv()
    return os.getenv("llamaParse")

# Define schema classes
class Experience(BaseModel):
    company: str = Field(description="Company name")
    role: str = Field(description="Job title")
    start_date: Optional[str] = Field(description="Start date", default=None)
    end_date: Optional[str] = Field(description="End date", default=None)
    description: Optional[str] = Field(description="Job description", default=None)

class Education(BaseModel):
    institution: str = Field(description="School or university")
    degree: Optional[str] = Field(description="Degree or qualification", default=None)
    start_date: Optional[str] = Field(description="Start date", default=None)
    end_date: Optional[str] = Field(description="End date", default=None)

class Resume(BaseModel):
    name: Optional[str] = Field(description="Full name", default=None)
    email: Optional[str] = Field(description="Email address", default=None)
    phone: Optional[str] = Field(description="Phone number", default=None)
    summary: Optional[str] = Field(description="Profile summary", default=None)
    work_experience: Optional[List[Experience]] = Field(description="List of work experiences", default=None)
    education: Optional[List[Education]] = Field(description="Educational background", default=None)
    skills: Optional[List[str]] = Field(description="Technical skills", default=None)
    soft_skills: Optional[List[str]] = Field(description="Soft skills like problem solving, teamwork, etc.", default=None)
    certifications: Optional[List[str]] = Field(description="Certifications", default=None)
    projects: Optional[List[str]] = Field(description="Projects", default=None)
    languages: Optional[List[str]] = Field(description="Languages", default=None)
    hobbies: Optional[List[str]] = Field(description="Hobbies or interests", default=None)
    other: Optional[str] = Field(description="Other relevant info", default=None)

# Create extractor and agent
def create_resume_agent():
    mykey = get_llama_key()
    extractor = LlamaExtract(mykey)
    agent = extractor.get_agent(name="resume-parser_v2")
    return agent

# Extract resume data from a file
def extract_resume(file_path: str):
    agent = create_resume_agent()
    result = agent.extract(file_path)
    return result.data

# Pretty print extracted data
def print_resume_data(data):
    print(json.dumps(data, indent=2))
