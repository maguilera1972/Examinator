"""Certification vendors and non-Microsoft family definitions."""

MICROSOFT_VENDOR = "Microsoft"
COMPTIA_VENDOR = "CompTIA"

VENDOR_DEFINITIONS = [
    {
        "slug": "microsoft",
        "name": "Microsoft",
        "description": (
            "Microsoft certifications across Azure, AI, security, Microsoft 365, "
            "data, Power Platform, Dynamics 365, and GitHub."
        ),
        "sort_order": 10,
        "hub_url": "https://learn.microsoft.com/en-us/credentials/",
        "logo_url": "/static/img/vendors/microsoft.svg",
    },
    {
        "slug": "comptia",
        "name": "CompTIA",
        "description": (
            "Vendor-neutral CompTIA certifications from Tech+ and A+ through Network+, "
            "Security+, Cloud+, Linux+, Server+, Project+, CySA+, and DataAI."
        ),
        "sort_order": 20,
        "hub_url": "https://www.comptia.org/certifications",
        "logo_url": "/static/img/vendors/comptia.svg",
    },
]

COMPTIA_FAMILY_DEFINITIONS = [
    {
        "code": "TEC",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Tech+",
        "theme": "Core IT",
        "description": "Foundational IT concepts for students and career changers entering technology roles.",
        "sort_order": 5,
    },
    {
        "code": "APL",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA A+",
        "theme": "Core IT",
        "description": "Entry-level certification for IT support, hardware, software, and troubleshooting.",
        "sort_order": 10,
    },
    {
        "code": "NET",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Network+",
        "theme": "Infrastructure",
        "description": "Networking concepts, implementation, operations, and security for wired and wireless networks.",
        "sort_order": 20,
    },
    {
        "code": "SEC",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Security+",
        "theme": "Cybersecurity",
        "description": "Baseline cybersecurity skills for threat management, architecture, and operations.",
        "sort_order": 30,
    },
    {
        "code": "CLO",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Cloud+",
        "theme": "Cloud",
        "description": "Cloud architecture, deployment, operations, and security across hybrid environments.",
        "sort_order": 40,
    },
    {
        "code": "LIN",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Linux+",
        "theme": "Infrastructure",
        "description": "Linux system administration, security, scripting, and automation.",
        "sort_order": 50,
    },
    {
        "code": "SRV",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Server+",
        "theme": "Infrastructure",
        "description": "Server hardware, virtualization, storage, and datacenter operations.",
        "sort_order": 55,
    },
    {
        "code": "PRJ",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Project+",
        "theme": "Professional Skills",
        "description": "Project management concepts, tools, and lifecycle for IT and business initiatives.",
        "sort_order": 60,
    },
    {
        "code": "CYB",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA CySA+",
        "theme": "Cybersecurity",
        "description": "Cybersecurity analytics, threat detection, and response for security operations.",
        "sort_order": 70,
    },
    {
        "code": "DAI",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA DataAI",
        "theme": "Data & Analytics",
        "description": "Data literacy, analytics, and responsible AI for business and technical roles.",
        "sort_order": 80,
    },
    {
        "code": "PEN",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA PenTest+",
        "theme": "Cybersecurity",
        "description": "Penetration testing, vulnerability assessment, and ethical hacking techniques.",
        "sort_order": 90,
    },
    {
        "code": "DAT",
        "vendor": COMPTIA_VENDOR,
        "name": "CompTIA Data+",
        "theme": "Data & Analytics",
        "description": "Data mining, visualization, governance, and analysis for business insights.",
        "sort_order": 95,
    },
]

COMPTIA_EXAM_CATALOG = {
    "FC0-U71": {
        "family_code": "TEC",
        "name": "CompTIA Tech+",
        "level": "Foundational",
        "duration": 60,
        "passing": 650,
        "overview": "Technology concepts, software, hardware, security, and troubleshooting fundamentals.",
        "learn_url": "https://www.comptia.org/certifications/tech",
    },
    "220-1101": {
        "family_code": "APL",
        "name": "CompTIA A+ Core 1",
        "level": "Associate",
        "duration": 90,
        "passing": 675,
        "overview": "Mobile devices, networking technology, hardware, virtualization, cloud computing, and troubleshooting.",
        "learn_url": "https://www.comptia.org/certifications/a",
    },
    "220-1102": {
        "family_code": "APL",
        "name": "CompTIA A+ Core 2",
        "level": "Associate",
        "duration": 90,
        "passing": 675,
        "overview": "Operating systems, security, software troubleshooting, and operational procedures.",
        "learn_url": "https://www.comptia.org/certifications/a",
    },
    "N10-009": {
        "family_code": "NET",
        "name": "CompTIA Network+",
        "level": "Associate",
        "duration": 90,
        "passing": 720,
        "overview": "Networking fundamentals, implementations, operations, and security.",
        "learn_url": "https://www.comptia.org/certifications/network",
    },
    "SY0-701": {
        "family_code": "SEC",
        "name": "CompTIA Security+",
        "level": "Associate",
        "duration": 90,
        "passing": 750,
        "overview": "General security concepts, threats, architecture, operations, and program management.",
        "learn_url": "https://www.comptia.org/certifications/security",
    },
    "CV0-004": {
        "family_code": "CLO",
        "name": "CompTIA Cloud+",
        "level": "Associate",
        "duration": 90,
        "passing": 750,
        "overview": "Cloud architecture, security, deployment, operations, and troubleshooting.",
        "learn_url": "https://www.comptia.org/certifications/cloud",
    },
    "XK0-005": {
        "family_code": "LIN",
        "name": "CompTIA Linux+",
        "level": "Associate",
        "duration": 90,
        "passing": 720,
        "overview": "Linux administration, security, automation, and troubleshooting.",
        "learn_url": "https://www.comptia.org/certifications/linux",
    },
    "SK0-005": {
        "family_code": "SRV",
        "name": "CompTIA Server+",
        "level": "Associate",
        "duration": 90,
        "passing": 750,
        "overview": "Server hardware, storage, virtualization, disaster recovery, and datacenter operations.",
        "learn_url": "https://www.comptia.org/certifications/server",
    },
    "PK0-005": {
        "family_code": "PRJ",
        "name": "CompTIA Project+",
        "level": "Associate",
        "duration": 90,
        "passing": 710,
        "overview": "Project basics, constraints, communication, tools, and change management.",
        "learn_url": "https://www.comptia.org/certifications/project",
    },
    "CS0-003": {
        "family_code": "CYB",
        "name": "CompTIA CySA+",
        "level": "Associate",
        "duration": 165,
        "passing": 750,
        "overview": "Security analytics, intrusion detection, and response in enterprise environments.",
        "learn_url": "https://www.comptia.org/certifications/cysa",
    },
    "DY0-001": {
        "family_code": "DAI",
        "name": "CompTIA DataAI",
        "level": "Associate",
        "duration": 165,
        "passing": 700,
        "overview": "Data concepts, analytics workflows, AI fundamentals, and responsible AI practices.",
        "learn_url": "https://www.comptia.org/certifications/dataai",
    },
    "PT0-003": {
        "family_code": "PEN",
        "name": "CompTIA PenTest+",
        "level": "Associate",
        "duration": 165,
        "passing": 750,
        "overview": "Planning, scoping, and performing penetration tests and vulnerability management.",
        "learn_url": "https://www.comptia.org/certifications/pentest",
    },
    "DA0-001": {
        "family_code": "DAT",
        "name": "CompTIA Data+",
        "level": "Associate",
        "duration": 90,
        "passing": 675,
        "overview": "Data concepts, mining, analysis, visualization, and governance.",
        "learn_url": "https://www.comptia.org/certifications/data",
    },
}

VENDOR_BY_SLUG = {v["slug"]: v for v in VENDOR_DEFINITIONS}
VENDOR_SLUG_BY_NAME = {v["name"]: v["slug"] for v in VENDOR_DEFINITIONS}


def vendor_slug(vendor_name: str) -> str:
    return VENDOR_SLUG_BY_NAME.get(vendor_name, vendor_name.lower().replace(" ", "-"))
