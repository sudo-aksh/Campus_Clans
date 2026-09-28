from django.core.management.base import BaseCommand
from campus_clans.models import SkillType, Skill

skills_matrix = {
    "software_and_advanced_computing": [
        "Python",
        "R",
        "Java",
        "C++",
        "TypeScript",
        "DSA",
        "OOPs",
        "DBMS",
        "Operating Systems",
        "TensorFlow",
        "PyTorch",
        "Scikit-Learn",
        "Prompt Engineering",
        "Generative AI",
        "HTML / CSS",
        "JavaScript",
        "MERN",
        "Next.js",
        "Django / Flask",
        "GCP",
        "AWS",
        "Docker",
        "Git / GitHub",
        "REST APIs",
        "Software Testing"
    ],
    "cyber_security_and_networks": [
        "Network Security",
        "Ethical Hacking",
        "Penetration Testing",
        "Cryptography",
        "Digital Forensics",
        "CCNA / Routing & Switching",
        "IoT",
        "Embedded C",
        "Arduino / Raspberry Pi",
        "PCB Design",
        "PLC Automation",
        "Robotics"
    ],
    "mechanical_automotive_and_industrial": [
        "AutoCAD",
        "SolidWorks",
        "CATIA",
        "ANSYS / FEA",
        "MATLAB / Simulink",
        "Fusion 360",
        "Engine Diagnostics",
        "EV Technology",
        "CNC",
        "Hydraulics & Pneumatics",
        "QA / QC"
    ],
    "fintech_banking_and_finance": [
        "Financial Analysis",
        "Equity Research",
        "Wealth Management",
        "Retail Banking",
        "Stock Market Analysis",
        "Blockchain / Smart Contracts",
        "KYC Processes"
    ],
    "business_operations_and_sales": [
        "Financial Modeling",
        "Taxation / GST",
        "Tally Prime",
        "Excel / VBA",
        "Bookkeeping",
        "Digital Marketing",
        "SEO",
        "SEM",
        "Meta / Google Ads",
        "Lead Generation",
        "B2B Sales",
        "B2C Sales",
        "CRM",
        "Agile / Scrum",
        "Product Management",
        "HR Operations",
        "Talent Acquisition",
        "PR",
        "Brand Strategy"
    ],
    "consulting_and_business_strategy": [
        "Management Consulting",
        "Business Analytics",
        "Market Sizing",
        "Presentation Design",
        "Competitive Intelligence"
    ],
    "law_compliance_and_ipr": [
        "Corporate Law",
        "Contract Drafting",
        "IPR Filing",
        "Patent Search",
        "Data Privacy"
    ],
    "renewable_energy_and_esg": [
        "Carbon Footprint",
        "ESG Reporting",
        "Solar / Wind Systems",
        "Circular Economy",
        "Life Cycle Assessment"
    ],
    "hospitality_events_and_tourism": [
        "Event Management",
        "Crowd Management",
        "F&B Operations",
        "FSSAI Safety",
        "Guest Relations",
        "Front Office",
        "Travel Planning",
        "Banqueting"
    ],
    "content_media_and_journalism": [
        "Content Writing",
        "Copywriting",
        "Technical Writing",
        "Creative Writing",
        "Scriptwriting",
        "Journalism",
        "Presentation / Anchoring",
        "Editing & Proofreading",
        "Audio / Voiceover",
        "Podcast Editing",
        "Social Media",
        "Public Speaking",
        "Photography"
    ],
    "creative_arts_design_and_multimedia": [
        "Premiere Pro",
        "DaVinci Resolve",
        "Photoshop",
        "Lightroom",
        "Illustrator",
        "Canva",
        "Figma",
        "Blender",
        "Maya",
        "After Effects",
        "Rigging",
        "VFX",
        "Unity",
        "Unreal Engine",
        "Illustration",
        "Garment Construction",
        "Textile Styling",
        "Architectural Drafting",
        "Interior Rendering",
        "Painting",
        "Ceramics / Sculpting"
    ],
    "applied_sciences_pharma_and_healthcare": [
        "PCR",
        "Gel Electrophoresis",
        "HPLC",
        "Microbial Culturing",
        "Spectroscopy",
        "ELISA",
        "Pharmacology",
        "Drug Dispensing",
        "Clinical Trials",
        "Pharma Marketing",
        "Nutrition Planning",
        "HACCP",
        "EIA",
        "Waste Management",
        "Biosafety",
        "Medical Transcription"
    ],
    "agriculture_and_agri_business": [
        "Hydroponics",
        "Precision Agriculture",
        "Soil Testing",
        "Water Analysis",
        "Pest Management",
        "Plant Disease Diagnosis",
        "Farm Operations",
        "Agricultural Supply Chain"
    ],
    "forensic_science_and_criminology": [
        "Fingerprint Matching",
        "DNA Extraction",
        "Cyber Forensics",
        "Crime Scene Documentation",
        "Forensic Ballistics",
        "Toxicology",
        "Handwriting Verification"
    ],
    "humanities_social_sciences_and_research": [
        "Psychometric Testing",
        "Counseling Basics",
        "Policy Analysis",
        "Economic Modeling",
        "Market Research",
        "Survey Design",
        "Qualitative Research",
        "Archival Research"
    ],
    "education_sports_and_information_management": [
        "Lesson Planning",
        "Child Psychology",
        "Curriculum Design",
        "Classroom Management",
        "Sports Coaching",
        "First Aid / CPR",
        "Fitness Training",
        "Library Cataloging",
        "Metadata Indexing",
        "Digital Archiving",
        "Moodle Administration"
    ],
    "universal_soft_skills": [
        "Communication",
        "Email / Slack Etiquette",
        "Negotiation",
        "Leadership & Delegation",
        "Conflict Resolution",
        "Time Management",
        "Critical Thinking",
        "Problem Solving",
        "Cross-Cultural Collaboration",
        "Emotional Intelligence",
        "Stress Management",
        "Adaptability"
    ]
}


# skills_matrix = {
#     "software_and_advanced_computing": [
#         "Data Structures & Algorithms (DSA)",
#         "Object-Oriented Programming (OOPs)",
#         "Database Management Systems (DBMS)",
#         "Operating Systems (Linux/Windows)",
#         "Python Programming",
#         "R Programming",
#         "Java Development",
#         "C++ Programming",
#         "TensorFlow",
#         "PyTorch",
#         "Scikit-Learn",
#         "Prompt Engineering",
#         "Generative AI Basics",
#         "Data Visualization (Tableau/PowerBI)",
#         "Google Cloud Platform (GCP) Basics",
#         "Amazon Web Services (AWS) Basics",
#         "Docker Containerization",
#         "HTML5 & CSS3",
#         "JavaScript (ES6+)",
#         "TypeScript",
#         "MERN Stack (MongoDB, Express, React, Node)",
#         "Next.js Framework",
#         "Django / Flask (Python Web Dev)",
#         "REST APIs Development",
#         "Git & GitHub Version Control",
#         "Software Testing Basics"
#     ],
#     "cyber_security_and_network_infrastructure": [
#         "Network Security Protocols",
#         "Ethical Hacking Basics",
#         "Penetration Testing (Kali Linux)",
#         "Cryptography & Encryption Standards",
#         "Digital Forensics Basics",
#         "Microcontrollers (Arduino/Raspberry Pi)",
#         "Embedded C Programming",
#         "PCB Design Basics (Altium/Eagle)",
#         "Routing & Switching (CCNA)",
#         "IoT Prototyping",
#         "PLC Automation Basics",
#         "Robotics Programming"
#     ],
#     "mechanical_automotive_and_industrial_tech": [
#         "AutoCAD Draftsmanship",
#         "SolidWorks 3D Modeling",
#         "CATIA Surface Designing",
#         "ANSYS Finite Element Analysis (FEA)",
#         "MATLAB & Simulink",
#         "Fusion 360 Prototyping",
#         "Automotive Engine Diagnostics",
#         "Electric Vehicle (EV) Basics",
#         "CNC Programming Basics",
#         "Hydraulics & Pneumatics",
#         "Quality Inspection (QA/QC Basics)"
#     ],
#     "fintech_banking_and_financial_services": [
#         "Financial Statement Analysis",
#         "Equity Research Basics",
#         "Wealth Management Basics",
#         "Retail Banking Basics",
#         "Stock Market Technical Analysis",
#         "Blockchain & Smart Contract Basics",
#         "KYC Verification Processes"
#     ],
#     "business_operations_management_and_sales": [
#         "Financial Modeling & Valuation",
#         "Corporate Taxation & GST Basics",
#         "Tally Prime ERP",
#         "Advanced Excel (VBA, Macros, Pivot Tables)",
#         "Double-Entry Bookkeeping",
#         "Digital Marketing Strategy",
#         "SEO (Search Engine Optimization)",
#         "SEM (Search Engine Marketing)",
#         "Meta Ads & Google Ads Management",
#         "Business Development (Lead Generation)",
#         "B2B Sales Pitching",
#         "B2C Retail Sales Pitching",
#         "CRM Operations (HubSpot/Salesforce)",
#         "Project Management Basics (Agile/Scrum)",
#         "Product Management Basics",
#         "Human Resource Operations (HRIS)",
#         "Talent Acquisition & Sourcing",
#         "Public Relations (PR) & Media Strategy",
#         "Brand Strategy Basics"
#     ],
#     "corporate_consulting_and_business_strategy": [
#         "Management Consulting Frameworks",
#         "Data-Driven Business Analytics",
#         "Market Sizing & Guesstimate Solving",
#         "Corporate Presentation Design",
#         "Competitive Intelligence Analysis"
#     ],
#     "corporate_law_compliance_and_ipr": [
#         "Corporate Law Frameworks",
#         "Commercial Contract Drafting",
#         "Intellectual Property Rights (IPR) Filing",
#         "Patent Search & Analytics",
#         "Data Privacy Basics (GDPR/DPDP)"
#     ],
#     "renewable_energy_and_esg_operations": [
#         "Carbon Footprint Estimation",
#         "ESG Framework Reporting (GRI/SASB)",
#         "Renewable Energy Systems Design (Solar/Wind)",
#         "Circular Economy Principles",
#         "Life Cycle Assessment (LCA) Basics"
#     ],
#     "hospitality_event_and_tourism_management": [
#         "Event Logistics & Execution",
#         "Crowd Management Basics",
#         "Food & Beverage (F&B) Operations",
#         "Restaurant Safety Standards (FSSAI)",
#         "Guest Relations & Hospitality CRM",
#         "Front Office Operations",
#         "Travel & Tourism Itinerary Planning",
#         "Banqueting & Event Coordination"
#     ],
#     "content_creation_media_and_journalism": [
#         "Content Writing & Blogging",
#         "Copywriting for Conversions",
#         "Technical Writing & Documentation",
#         "SEO Content Optimization",
#         "Creative Writing",
#         "Scriptwriting & Storyboarding",
#         "News Reporting & Field Journalism",
#         "Anchor-Handling & Presenting",
#         "Copyediting & Proofreading",
#         "Audio Production & Voiceover",
#         "Podcast Editing",
#         "Social Media Content Strategy",
#         "Public Speaking",
#         "Photojournalism & Photography"
#     ],
#     "creative_arts_design_and_multimedia": [
#         "Video Editing (Adobe Premiere Pro)",
#         "Color Grading (DaVinci Resolve)",
#         "Photo Editing (Adobe Photoshop)",
#         "Digital Retouching (Lightroom)",
#         "Vector Graphic Design (Adobe Illustrator)",
#         "Quick Graphic Creation (Canva)",
#         "UI/UX Visual Design (Figma)",
#         "Interactive Prototyping (Adobe XD)",
#         "User Research & Usability Testing",
#         "Motion Graphics Design (After Effects)",
#         "3D Assets Modeling (Blender)",
#         "3D Design (Autodesk Maya)",
#         "Game Engine Architecture (Unity)",
#         "Game Development Basics (Unreal Engine)",
#         "Character Rigging Basics",
#         "VFX Compositing Basics",
#         "Fashion Illustration & Sketching",
#         "Garment Construction & Draping",
#         "Textile Styling",
#         "Spatial Planning & Architectural Drafting",
#         "3D Interior Rendering (SketchUp / V-Ray)",
#         "Fine Arts & Painting",
#         "Sculpting & Ceramics Molding"
#     ],
#     "applied_sciences_pharma_and_healthcare": [
#         "PCR Testing Operations",
#         "Gel Electrophoresis Analysis",
#         "Liquid Chromatography Basics (HPLC)",
#         "Microbial Culturing & Isolation",
#         "UV-Visible & FTIR Spectroscopy",
#         "Clinical Pharmacology Basics",
#         "Drug Dispensing Basics",
#         "Clinical Trials Coordination",
#         "Pharmaceutical Marketing",
#         "Diet Chart & Nutrition Planning",
#         "Food Safety Management (HACCP)",
#         "Environmental Impact Assessment (EIA)",
#         "Waste Management Basics",
#         "Laboratory Biosafety Compliance",
#         "Medical Transcription",
#         "Immunological Assays (ELISA)"
#     ],
#     "agriculture_and_agri_business": [
#         "Hydroponics & Vertical Farming Setups",
#         "Precision Agriculture Basics",
#         "Soil Health & Nutrient Testing",
#         "Water Quality Analysis",
#         "Pest Management Basics (IPM)",
#         "Plant Disease Diagnosis",
#         "Farm Operations Management",
#         "Agricultural Supply Chain Basics"
#     ],
#     "forensic_science_and_criminology": [
#         "Latent Fingerprint Matching",
#         "Forensic DNA Extraction Basics",
#         "Cyber Forensics & Drive Imaging",
#         "Crime Scene Investigation Documentation",
#         "Forensic Ballistics Tracking",
#         "Toxicology Screening Basics",
#         "Handwriting Verification"
#     ],
#     "humanities_social_sciences_and_research": [
#         "Psychometric Test Administration",
#         "Active Listening & Counseling Basics",
#         "Statistical Policy Analysis",
#         "Economic Modeling Basics",
#         "Market Research & Consumer Demographics",
#         "Quantitative Survey Design",
#         "Qualitative Data Collection",
#         "Archival Research & Documentation"
#     ],
#     "education_sports_and_info_management": [
#         "Pedagogical Lesson Planning",
#         "Child Psychology Concepts",
#         "Curriculum Design Basics",
#         "Classroom Management Techniques",
#         "Sports Coaching & Officiating",
#         "First Aid & CPR Application",
#         "Physical Fitness Training",
#         "Library Cataloging (DDC/CC)",
#         "Metadata Indexing Standards",
#         "Digital Archiving & Preservation",
#         "E-Learning Platforms Administration (Moodle)"
#     ],
#     "universal_soft_skills_and_competencies": [
#         "Interpersonal Verbal Communication",
#         "Corporate Email Etiquette & Slack Ops",
#         "Commercial Negotiation Basics",
#         "Team Leadership & Delegation",
#         "Conflict Resolution & Mediation",
#         "Time Management & Prioritization",
#         "Critical Lateral Thinking",
#         "Root-Cause Analytical Problem Solving",
#         "Cross-Cultural Team Collaboration",
#         "Emotional Intelligence (EQ)",
#         "Stress Management & Work Resilience",
#         "Adaptive Learning & Adaptability"
#     ]
# }

class Command(BaseCommand):

    help = "Load Campus Clans skill catalogue"

    def handle(self, *args, **kwargs):

        for skill_type_key, skills in skills_matrix.items():

            display_name = (
                skill_type_key
                .replace("_", " ")
                .title()
            )

            skill_type, created = SkillType.objects.get_or_create(
                name=display_name
            )

            for skill_name in skills:

                Skill.objects.get_or_create(
                    skill_type=skill_type,
                    name=skill_name
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Skill catalogue loaded successfully."
            )
        )