import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from jinja2 import Template
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        
    async def send_email(
        self, 
        to_emails: List[str], 
        subject: str, 
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """Send email with both HTML and text content"""
        
        if not all([self.smtp_host, self.smtp_user, self.smtp_password]):
            logger.warning("Email configuration incomplete, skipping email send")
            return False
        
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.from_email
            message["To"] = ", ".join(to_emails)
            
            # Add text part
            if text_content:
                text_part = MIMEText(text_content, "plain")
                message.attach(text_part)
            
            # Add HTML part
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Create secure SSL context
            context = ssl.create_default_context()
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_emails, message.as_string())
            
            logger.info(f"Email sent successfully to {', '.join(to_emails)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    async def send_task_assignment_notification(
        self, 
        assignee_email: str, 
        assignee_name: str,
        task_title: str, 
        task_description: str,
        due_date: Optional[str] = None,
        priority: str = "medium",
        assigner_name: str = "System"
    ) -> bool:
        """Send task assignment notification email"""
        
        html_template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }
                .content { padding: 20px 0; }
                .task-details { background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }
                .priority-high { color: #dc3545; font-weight: bold; }
                .priority-medium { color: #fd7e14; font-weight: bold; }
                .priority-low { color: #28a745; font-weight: bold; }
                .footer { text-align: center; font-size: 12px; color: #6c757d; margin-top: 30px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 New Compliance Task Assigned</h1>
                </div>
                
                <div class="content">
                    <p>Hello {{ assignee_name }},</p>
                    
                    <p>You have been assigned a new compliance task by {{ assigner_name }}:</p>
                    
                    <div class="task-details">
                        <h3>{{ task_title }}</h3>
                        <p><strong>Description:</strong> {{ task_description }}</p>
                        <p><strong>Priority:</strong> <span class="priority-{{ priority }}">{{ priority.upper() }}</span></p>
                        {% if due_date %}
                        <p><strong>Due Date:</strong> {{ due_date }}</p>
                        {% endif %}
                    </div>
                    
                    <p>Please log into the AI Compliance platform to review the task details and begin work.</p>
                    
                    <p>Best regards,<br>
                    AI Compliance Team</p>
                </div>
                
                <div class="footer">
                    <p>This is an automated notification from AI Compliance Management System</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        html_content = html_template.render(
            assignee_name=assignee_name,
            task_title=task_title,
            task_description=task_description,
            due_date=due_date,
            priority=priority,
            assigner_name=assigner_name
        )
        
        text_content = f"""
        New Compliance Task Assigned
        
        Hello {assignee_name},
        
        You have been assigned a new compliance task by {assigner_name}:
        
        Task: {task_title}
        Description: {task_description}
        Priority: {priority.upper()}
        {f"Due Date: {due_date}" if due_date else ""}
        
        Please log into the AI Compliance platform to review the task details.
        
        Best regards,
        AI Compliance Team
        """
        
        return await self.send_email(
            [assignee_email],
            f"New Compliance Task: {task_title}",
            html_content,
            text_content
        )
    
    async def send_compliance_alert(
        self,
        user_emails: List[str],
        alert_type: str,
        message: str,
        jurisdiction: Optional[str] = None,
        severity: str = "medium"
    ) -> bool:
        """Send compliance alert notification"""
        
        html_template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .alert-header { padding: 20px; border-radius: 8px; text-align: center; }
                .alert-high { background-color: #f8d7da; border: 1px solid #f1aeb5; }
                .alert-medium { background-color: #fff3cd; border: 1px solid #ffeaa7; }
                .alert-low { background-color: #d1ecf1; border: 1px solid #bee5eb; }
                .content { padding: 20px 0; }
                .footer { text-align: center; font-size: 12px; color: #6c757d; margin-top: 30px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="alert-header alert-{{ severity }}">
                    <h1>⚠️ Compliance Alert: {{ alert_type }}</h1>
                    {% if jurisdiction %}
                    <p><strong>Jurisdiction:</strong> {{ jurisdiction }}</p>
                    {% endif %}
                </div>
                
                <div class="content">
                    <p>{{ message }}</p>
                    
                    <p>Please review your compliance status and take appropriate action if necessary.</p>
                    
                    <p>Best regards,<br>
                    AI Compliance Team</p>
                </div>
                
                <div class="footer">
                    <p>This is an automated alert from AI Compliance Management System</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        html_content = html_template.render(
            alert_type=alert_type,
            message=message,
            jurisdiction=jurisdiction,
            severity=severity
        )
        
        text_content = f"""
        Compliance Alert: {alert_type}
        {f"Jurisdiction: {jurisdiction}" if jurisdiction else ""}
        
        {message}
        
        Please review your compliance status and take appropriate action if necessary.
        
        Best regards,
        AI Compliance Team
        """
        
        return await self.send_email(
            user_emails,
            f"Compliance Alert: {alert_type}",
            html_content,
            text_content
        )
    
    async def send_document_analysis_complete(
        self,
        user_email: str,
        user_name: str,
        document_name: str,
        analysis_summary: str,
        compliance_score: Optional[float] = None
    ) -> bool:
        """Send notification when document analysis is complete"""
        
        html_template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #28a745; color: white; padding: 20px; border-radius: 8px; text-align: center; }
                .content { padding: 20px 0; }
                .analysis-box { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }
                .score-box { background-color: #e7f3ff; padding: 10px; border-radius: 5px; text-align: center; }
                .footer { text-align: center; font-size: 12px; color: #6c757d; margin-top: 30px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📄 Document Analysis Complete</h1>
                </div>
                
                <div class="content">
                    <p>Hello {{ user_name }},</p>
                    
                    <p>The AI analysis of your document <strong>{{ document_name }}</strong> has been completed.</p>
                    
                    {% if compliance_score %}
                    <div class="score-box">
                        <h3>Compliance Score: {{ compliance_score }}%</h3>
                    </div>
                    {% endif %}
                    
                    <div class="analysis-box">
                        <h4>Analysis Summary:</h4>
                        <p>{{ analysis_summary }}</p>
                    </div>
                    
                    <p>Please log into the AI Compliance platform to review the detailed analysis results and any recommended actions.</p>
                    
                    <p>Best regards,<br>
                    AI Compliance Team</p>
                </div>
                
                <div class="footer">
                    <p>This is an automated notification from AI Compliance Management System</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        html_content = html_template.render(
            user_name=user_name,
            document_name=document_name,
            analysis_summary=analysis_summary,
            compliance_score=compliance_score
        )
        
        text_content = f"""
        Document Analysis Complete
        
        Hello {user_name},
        
        The AI analysis of your document "{document_name}" has been completed.
        
        {f"Compliance Score: {compliance_score}%" if compliance_score else ""}
        
        Analysis Summary:
        {analysis_summary}
        
        Please log into the AI Compliance platform to review the detailed results.
        
        Best regards,
        AI Compliance Team
        """
        
        return await self.send_email(
            [user_email],
            f"Analysis Complete: {document_name}",
            html_content,
            text_content
        )


# Global instance
email_service = EmailService()