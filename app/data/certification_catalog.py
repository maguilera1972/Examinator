"""Microsoft certification families and exam metadata."""

POSTER_PDF_URL = "https://arch-center.azureedge.net/Credentials/Certification-Poster_en-us.pdf"
CREDENTIALS_HUB_URL = "https://learn.microsoft.com/en-us/credentials/"

FAMILY_DEFINITIONS = [
    {"code": "AZ", "name": "Microsoft Azure", "theme": "Cloud & AI Platforms",
     "description": "Azure certifications validate skills for designing, deploying, and operating cloud infrastructure, applications, networking, and hybrid solutions on Microsoft Azure.", "sort_order": 10},
    {"code": "AI", "name": "Azure AI & Machine Learning", "theme": "Cloud & AI Platforms",
     "description": "AI certifications cover artificial intelligence workloads, machine learning, computer vision, natural language processing, and generative AI on Azure.", "sort_order": 20},
    {"code": "DP", "name": "Azure Data & Microsoft Fabric", "theme": "Data & Analytics",
     "description": "Data certifications focus on databases, analytics, data engineering, and Microsoft Fabric workloads on Azure.", "sort_order": 30},
    {"code": "SC", "name": "Security, Compliance & Identity", "theme": "Security",
     "description": "Security certifications validate expertise in Microsoft Entra, Defender, Sentinel, compliance, and identity protection across the Microsoft cloud.", "sort_order": 40},
    {"code": "MS", "name": "Microsoft 365", "theme": "Modern Work",
     "description": "Microsoft 365 certifications cover tenant administration, Teams, collaboration, and productivity services for organizations.", "sort_order": 50},
    {"code": "MD", "name": "Microsoft 365 Endpoint", "theme": "Modern Work",
     "description": "Endpoint certifications validate skills for deploying, configuring, and managing Windows client devices in enterprise environments.", "sort_order": 55},
    {"code": "PL", "name": "Microsoft Power Platform", "theme": "Business Applications",
     "description": "Power Platform certifications cover building apps, automating workflows, analyzing data, and creating virtual agents with low-code tools.", "sort_order": 60},
    {"code": "MB", "name": "Dynamics 365", "theme": "Business Applications",
     "description": "Dynamics 365 certifications validate functional and technical skills for CRM, ERP, finance, supply chain, and customer experience solutions.", "sort_order": 70},
    {"code": "GH", "name": "GitHub", "theme": "Developer Tools",
     "description": "GitHub certifications validate skills for repository administration, Actions, Advanced Security, Copilot, and agentic AI development.", "sort_order": 80},
    {"code": "AB", "name": "AI Business & Copilot", "theme": "AI Business Solutions",
     "description": "AI Business certifications focus on Copilot adoption, AI transformation leadership, and designing agentic business solutions on Microsoft platforms.", "sort_order": 90},
]

LEARN_SLUGS = {
    "AZ-900": "azure-fundamentals", "AZ-104": "azure-administrator", "AZ-120": "azure-for-sap-workloads-specialty",
    "AZ-140": "azure-virtual-desktop-specialty", "AZ-204": "azure-developer", "AZ-305": "azure-solutions-architect",
    "AZ-400": "azure-devops-engineer", "AZ-500": "azure-security-engineer", "AZ-700": "azure-network-engineer-associate",
    "AZ-800": "windows-server-hybrid-administrator", "AZ-801": "windows-server-hybrid-administrator",
    "AZ-802": "windows-server-hybrid-administrator",
    "AI-900": "azure-ai-fundamentals", "AI-901": "azure-ai-fundamentals", "AI-102": "azure-ai-engineer",
    "AI-103": "azure-ai-apps-and-agents-developer-associate", "AI-200": "azure-ai-cloud-developer-associate",
    "AI-300": "azure-ai-engineer", "DP-900": "azure-data-fundamentals", "DP-300": "azure-database-administrator-associate",
    "DP-420": "azure-cosmos-db-developer-specialty", "DP-600": "fabric-analytics-engineer-associate",
    "DP-700": "fabric-data-engineer-associate", "DP-750": "fabric-data-engineer-associate",
    "DP-800": "fabric-analytics-engineer-associate", "SC-900": "security-compliance-and-identity-fundamentals",
    "SC-200": "security-operations-analyst", "SC-300": "identity-and-access-administrator",
    "SC-401": "information-protection-administrator", "SC-500": "azure-security-engineer",
    "SC-730": "security-operations-analyst", "SC-100": "cybersecurity-architect-expert",
    "MS-102": "microsoft-365-administrator-expert", "MS-700": "teams-administrator-associate",
    "MS-721": "collaboration-communications-systems-engineer", "MD-102": "endpoint-administrator",
    "PL-900": "power-platform-fundamentals", "PL-200": "power-platform-functional-consultant",
    "PL-300": "power-bi-data-analyst", "PL-400": "power-platform-developer-associate",
    "PL-500": "power-automate-rpa-developer", "PL-600": "power-platform-solution-architect-expert",
    "MB-230": "dynamics-365-customer-service-functional-consultant", "MB-240": "dynamics-365-field-service-functional-consultant",
    "MB-280": "dynamics-365-customer-experience-analyst", "MB-300": "dynamics-365-finance-functional-consultant",
    "MB-310": "dynamics-365-finance-functional-consultant", "MB-330": "dynamics-365-supply-chain-management-functional-consultant",
    "MB-335": "dynamics-365-supply-chain-management-functional-consultant",
    "MB-500": "dynamics-365-finance-and-operations-apps-developer", "MB-700": "dynamics-365-finance-functional-consultant",
    "MB-800": "dynamics-365-business-central-functional-consultant", "MB-820": "dynamics-365-business-central-developer",
    "GH-900": "github-foundations", "GH-100": "github-administration", "GH-200": "github-actions",
    "GH-300": "github-copilot", "GH-500": "github-advanced-security", "GH-600": "github-certified-agentic-ai-developer",
    "AB-900": "ai-business-professional", "AB-730": "ai-transformation-leader", "AB-731": "ai-transformation-leader",
    "AB-100": "agentic-ai-business-solutions-architect", "AB-210": "ai-agent-builder-associate",
    "AB-250": "copilot-and-agent-administration-fundamentals", "AB-410": "agentic-ai-business-solutions-architect",
    "AB-620": "ai-business-professional",
}

EXAM_CATALOG = {
    "AZ-900": {"name": "Microsoft Certified: Azure Fundamentals", "level": "Fundamentals", "role": "Administrator", "product": "Azure", "duration": 65, "passing": 700,
        "sections": [("Describe cloud concepts", 25, "Core cloud models, benefits, and consumption-based economics."),
            ("Describe Azure architecture and services", 35, "Compute, networking, storage, and core Azure services."),
            ("Describe Azure management and governance", 30, "Management tools, governance, and security fundamentals.")]},
    "AZ-104": {"name": "Microsoft Certified: Azure Administrator Associate", "level": "Associate", "role": "Administrator", "product": "Azure", "duration": 120, "passing": 700,
        "sections": [("Manage Azure identities and governance", 20, "Microsoft Entra ID, RBAC, subscriptions, and governance."),
            ("Implement and manage storage", 20, "Storage accounts, blobs, files, and backup."),
            ("Deploy and manage Azure compute resources", 25, "VMs, containers, and app services."),
            ("Implement and manage virtual networking", 20, "VNets, DNS, VPN, and load balancing."),
            ("Monitor and maintain Azure resources", 15, "Azure Monitor, alerts, and operational health.")]},
    "AZ-305": {"name": "Microsoft Certified: Azure Solutions Architect Expert", "level": "Expert", "role": "Solution Architect", "product": "Azure", "duration": 120, "passing": 700,
        "sections": [("Design identity, governance, and monitoring solutions", 25, None), ("Design data storage solutions", 20, None),
            ("Design business continuity solutions", 15, None), ("Design infrastructure solutions", 25, None),
            ("Design application architecture solutions", 15, None)]},
    "AI-900": {"name": "Microsoft Certified: Azure AI Fundamentals", "level": "Fundamentals", "role": "AI Engineer", "product": "Azure", "duration": 60, "passing": 700,
        "sections": [("Describe Artificial Intelligence workloads and considerations", 20, "Responsible AI and common AI workloads."),
            ("Describe fundamental principles of machine learning on Azure", 25, "ML concepts and Azure Machine Learning basics."),
            ("Describe features of computer vision workloads on Azure", 20, "Vision APIs and Azure AI Vision capabilities."),
            ("Describe features of Natural Language Processing workloads on Azure", 20, "Language understanding and speech services."),
            ("Describe features of generative AI workloads on Azure", 15, "Azure OpenAI and Copilot foundations.")]},
    "SC-900": {"name": "Microsoft Certified: Security, Compliance, and Identity Fundamentals", "level": "Fundamentals", "role": "Administrator", "product": "Security", "duration": 60, "passing": 700,
        "sections": [("Describe the concepts of security, compliance, and identity", 25, "Zero Trust and defense in depth."),
            ("Describe the capabilities of Microsoft Entra", 30, "Identity, access, and authentication services."),
            ("Describe the capabilities of Microsoft security solutions", 25, "Defender and security operations."),
            ("Describe the capabilities of Microsoft compliance solutions", 20, "Compliance Manager and information protection.")]},
    "MS-102": {"name": "Microsoft 365 Certified: Administrator Expert", "level": "Expert", "role": "Administrator", "product": "Microsoft 365", "duration": 120, "passing": 700,
        "sections": [("Deploy and manage a Microsoft 365 tenant", 25, None), ("Implement and manage identity and access", 25, None),
            ("Manage security and threats", 25, None), ("Manage compliance", 25, None)]},
    "DP-900": {"name": "Microsoft Certified: Azure Data Fundamentals", "level": "Fundamentals", "role": "Data Engineer", "product": "Azure", "duration": 60, "passing": 700,
        "sections": [("Describe core data concepts", 25, "Relational, non-relational, and analytics workloads."),
            ("Identify considerations for relational data on Azure", 20, "Azure SQL and database services."),
            ("Describe considerations for non-relational data on Azure", 20, "Cosmos DB and storage options."),
            ("Describe an analytics workload on Azure", 35, "Synapse, Fabric, and data analytics pipelines.")]},
    "PL-900": {"name": "Microsoft Certified: Power Platform Fundamentals", "level": "Fundamentals", "role": "App Maker", "product": "Power Platform", "duration": 60, "passing": 700,
        "sections": [("Describe the business value of Power Platform", 20, None), ("Identify the core components of Power Platform", 25, None),
            ("Demonstrate the capabilities of Power BI", 15, None), ("Demonstrate the capabilities of Power Apps", 20, None),
            ("Demonstrate the capabilities of Power Automate", 20, None)]},
}

EXAM_NAMES = {
    "AZ-120": "Microsoft Certified: Azure for SAP Workloads Specialty", "AZ-140": "Microsoft Certified: Azure Virtual Desktop Specialty",
    "AZ-204": "Microsoft Certified: Azure Developer Associate", "AZ-400": "Microsoft Certified: Azure DevOps Engineer Expert",
    "AZ-500": "Microsoft Certified: Azure Security Engineer Associate", "AZ-700": "Microsoft Certified: Azure Network Engineer Associate",
    "AZ-800": "Microsoft Certified: Windows Server Administrator Associate", "AZ-801": "Microsoft Certified: Windows Server Administrator Associate",
    "AZ-802": "Microsoft Certified: Windows Server Administrator Associate",
    "AI-901": "Microsoft Certified: Azure AI Fundamentals", "AI-102": "Microsoft Certified: Azure AI Engineer Associate",
    "AI-103": "Microsoft Certified: Azure AI Apps and Agents Developer Associate", "AI-200": "Microsoft Certified: Azure AI Cloud Developer Associate (beta)",
    "AI-300": "Microsoft Certified: Azure AI Engineer Associate", "DP-300": "Microsoft Certified: Azure Database Administrator Associate",
    "DP-420": "Microsoft Certified: Azure Cosmos DB Developer Specialty", "DP-600": "Microsoft Certified: Fabric Analytics Engineer Associate",
    "DP-700": "Microsoft Certified: Fabric Data Engineer Associate", "DP-750": "Microsoft Certified: Fabric Data Engineer Associate",
    "DP-800": "Microsoft Certified: Fabric Analytics Engineer Associate", "SC-100": "Microsoft Certified: Cybersecurity Architect Expert",
    "SC-200": "Microsoft Certified: Security Operations Analyst Associate", "SC-300": "Microsoft Certified: Identity and Access Administrator Associate",
    "SC-401": "Microsoft Certified: Information Protection Administrator Associate", "SC-500": "Microsoft Certified: Azure Security Engineer Associate",
    "SC-730": "Microsoft Certified: Security Operations Analyst Associate", "MS-700": "Microsoft 365 Certified: Teams Administrator Associate",
    "MS-721": "Microsoft 365 Certified: Collaboration Communications Systems Engineer Associate", "MD-102": "Microsoft 365 Certified: Endpoint Administrator Associate",
    "PL-200": "Microsoft Certified: Power Platform Functional Consultant Associate", "PL-300": "Microsoft Certified: Power BI Data Analyst Associate",
    "PL-400": "Microsoft Certified: Power Platform Developer Associate", "PL-500": "Microsoft Certified: Power Automate RPA Developer Associate",
    "PL-600": "Microsoft Certified: Power Platform Solution Architect Expert",
    "MB-230": "Microsoft Certified: Dynamics 365 Customer Service Functional Consultant Associate",
    "MB-240": "Microsoft Certified: Dynamics 365 Field Service Functional Consultant Associate",
    "MB-280": "Microsoft Certified: Dynamics 365 Customer Experience Analyst Associate",
    "MB-300": "Microsoft Certified: Dynamics 365 Finance Functional Consultant Associate",
    "MB-310": "Microsoft Certified: Dynamics 365 Finance Functional Consultant Associate",
    "MB-330": "Microsoft Certified: Dynamics 365 Supply Chain Management Functional Consultant Associate",
    "MB-335": "Microsoft Certified: Dynamics 365 Supply Chain Management Functional Consultant Associate",
    "MB-500": "Microsoft Certified: Dynamics 365 Finance and Operations Apps Developer Associate",
    "MB-700": "Microsoft Certified: Dynamics 365 Finance Functional Consultant Associate",
    "MB-800": "Microsoft Certified: Dynamics 365 Business Central Functional Consultant Associate",
    "MB-820": "Microsoft Certified: Dynamics 365 Business Central Developer Associate",
    "GH-900": "GitHub Certified: Foundations", "GH-100": "GitHub Certified: Administration", "GH-200": "GitHub Certified: Actions",
    "GH-300": "GitHub Certified: Copilot", "GH-500": "GitHub Certified: Advanced Security", "GH-600": "GitHub Certified: Agentic AI Developer (beta)",
    "AB-900": "Microsoft Certified: AI Business Professional", "AB-730": "Microsoft Certified: AI Transformation Leader",
    "AB-731": "Microsoft Certified: AI Transformation Leader", "AB-100": "Microsoft Certified: Agentic AI Business Solutions Architect",
    "AB-210": "Microsoft Certified: AI Agent Builder Associate (beta)", "AB-250": "Microsoft 365 Certified: Copilot and Agent Administration Fundamentals",
    "AB-410": "Microsoft Certified: Agentic AI Business Solutions Architect", "AB-620": "Microsoft Certified: AI Business Professional",
}


def family_code_for_exam(exam_code: str) -> str:
    return exam_code.split("-")[0]


def default_level(exam_code: str) -> str:
    num = exam_code.split("-")[1]
    if num.startswith("9"):
        return "Fundamentals"
    if exam_code in ("AZ-305", "AZ-400", "SC-100", "MS-102", "PL-600", "AB-100", "AB-410"):
        return "Expert"
    if exam_code in ("AZ-120", "AZ-140", "DP-420"):
        return "Specialty"
    return "Associate"


def learn_url_for_slug(slug: str) -> str:
    return f"https://learn.microsoft.com/en-us/credentials/certifications/{slug}/"
