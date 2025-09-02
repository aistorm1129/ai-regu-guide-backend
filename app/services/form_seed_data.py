from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.form_question import FormQuestion, QuestionType
from app.database import get_db


async def seed_form_questions(db: AsyncSession):
    """Seed initial form questions"""
    
    # Check if questions already exist
    result = await db.execute(select(FormQuestion))
    existing_questions = result.scalars().all()
    
    if len(existing_questions) > 0:
        print("Form questions already seeded")
        return
    
    questions_data = [
        {
            "category": "AI System Classification",
            "question": "Does your organization use AI systems that are considered high-risk according to EU AI Act (e.g., biometric identification, critical infrastructure, employment decisions)?",
            "question_type": QuestionType.RADIO,
            "options": ["Yes, we use high-risk AI systems", "No, only limited-risk AI systems", "No AI systems currently", "Not sure"],
            "required": True,
            "help_text": "High-risk AI systems require stricter compliance requirements under EU AI Act",
            "order": 1,
            "jurisdictions": ["EU AI Act"]
        },
        {
            "category": "User Transparency",
            "question": "Does your organization inform users when they are interacting with an AI system?",
            "question_type": QuestionType.RADIO,
            "options": ["Always inform users", "Sometimes inform users", "Rarely inform users", "Never inform users"],
            "required": True,
            "help_text": "Transparency requirements apply to most AI systems",
            "order": 2,
            "jurisdictions": ["EU AI Act", "US AI Governance"]
        },
        {
            "category": "Human Oversight",
            "question": "Describe your current process for human review of AI system decisions, especially for high-impact decisions:",
            "question_type": QuestionType.TEXTAREA,
            "required": True,
            "help_text": "Human oversight is mandatory for high-risk AI systems",
            "order": 3,
            "jurisdictions": ["EU AI Act", "ISO/IEC 42001"]
        },
        {
            "category": "Data Governance",
            "question": "What type of data governance framework do you have for AI training data?",
            "question_type": QuestionType.SELECT,
            "options": [
                "Comprehensive framework with full lineage tracking",
                "Basic framework with limited tracking",
                "Informal processes only",
                "No formal data governance",
                "Not applicable - no AI training"
            ],
            "required": True,
            "help_text": "Data quality and governance are critical for AI compliance",
            "order": 4,
            "jurisdictions": ["US AI Governance", "ISO/IEC 42001"]
        },
        {
            "category": "Risk Assessment",
            "question": "How frequently does your organization conduct AI risk assessments?",
            "question_type": QuestionType.RADIO,
            "options": ["Quarterly", "Semi-annually", "Annually", "Only when required", "Never conducted"],
            "required": True,
            "help_text": "Regular risk assessments are required by most AI regulations",
            "order": 5,
            "jurisdictions": ["EU AI Act", "US AI Governance", "ISO/IEC 42001"]
        },
        {
            "category": "Documentation",
            "question": "What AI system documentation do you currently maintain?",
            "question_type": QuestionType.SELECT,
            "options": [
                "Complete technical documentation with version control",
                "Basic documentation covering main components",
                "Limited documentation for some systems only",
                "Minimal or no documentation maintained"
            ],
            "required": True,
            "help_text": "Comprehensive documentation is required for compliance",
            "order": 6,
            "jurisdictions": ["EU AI Act", "ISO/IEC 42001"]
        },
        {
            "category": "Training and Awareness",
            "question": "Describe your organization's AI ethics and compliance training program:",
            "question_type": QuestionType.TEXTAREA,
            "required": True,
            "help_text": "Staff training is essential for maintaining AI compliance",
            "order": 7,
            "jurisdictions": ["US AI Governance", "ISO/IEC 42001"]
        },
        {
            "category": "Incident Management",
            "question": "Do you have processes in place for handling AI system incidents or failures?",
            "question_type": QuestionType.RADIO,
            "options": ["Yes, comprehensive incident response plan", "Yes, basic incident handling", "Informal processes only", "No specific processes"],
            "required": True,
            "help_text": "Incident management is crucial for maintaining AI system reliability",
            "order": 8,
            "jurisdictions": ["EU AI Act", "US AI Governance"]
        },
        {
            "category": "Third-Party AI",
            "question": "Does your organization use third-party AI services or models?",
            "question_type": QuestionType.RADIO,
            "options": ["Yes, extensively", "Yes, for some applications", "Rarely", "No third-party AI"],
            "required": True,
            "help_text": "Third-party AI usage has specific compliance implications",
            "order": 9,
            "jurisdictions": ["EU AI Act", "US AI Governance", "ISO/IEC 42001"]
        },
        {
            "category": "Privacy and Data Protection",
            "question": "How do you ensure AI systems comply with data protection regulations?",
            "question_type": QuestionType.SELECT,
            "options": [
                "Comprehensive privacy-by-design approach",
                "Regular privacy impact assessments",
                "Basic data protection measures",
                "Limited privacy considerations",
                "No specific privacy measures for AI"
            ],
            "required": True,
            "help_text": "AI systems must comply with data protection laws like GDPR",
            "order": 10,
            "jurisdictions": ["EU AI Act", "US AI Governance"]
        }
    ]
    
    for question_data in questions_data:
        question = FormQuestion(**question_data)
        db.add(question)
    
    await db.commit()
    print(f"Seeded {len(questions_data)} form questions")


# Run seeding if this file is executed directly
if __name__ == "__main__":
    import asyncio
    from app.database import AsyncSessionLocal
    
    async def main():
        async with AsyncSessionLocal() as db:
            await seed_form_questions(db)
    
    asyncio.run(main())