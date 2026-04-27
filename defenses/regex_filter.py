"""
defenses/regex_filter.py
Regex-based input and output filters — replication of Tables 3 & 4 from Song & Lee (2026).

Each filter function returns:
    {"blocked": bool, "matched_pattern": str | None, "pattern_category": str | None}
"""

import re
from typing import Optional

# =========================================================================== #
#  INPUT filter patterns (Table 3)
# =========================================================================== #
INPUT_PATTERNS = {
    # ------- Role playing -------------------------------------------------- #
    "role_playing": [
        r"pretend you (are|were)",
        r"act as (if|though)? ?(you|an? )",
        r"you are now",
        r"roleplay as",
        r"imagine you('re| are)",
        r"let'?s? play a (game|scenario|role)",
    ],

    # ------- System override ----------------------------------------------- #
    "system_override": [
        r"ignore (previous|all|above|prior) (instructions?|guidelines?|rules?|constraints?)",
        r"disregard (your|the) (previous|system|safety)",
        r"forget (your|all) (instructions?|training|guidelines?)",
        r"override (safety|content|filter|restriction)",
        r"bypass (safety|filter|content|restriction)",
        r"jailbreak",
        r"DAN\b",
        r"do anything now",
        r"without (any |your )?(restrictions?|limitations?|guidelines?|filters?)",
    ],

    # ------- Hypothetical scenarios --------------------------------------- #
    "hypothetical_scenario": [
        r"hypothetically (speaking)?,?",
        r"in a (fictional|hypothetical|alternate|parallel) (world|universe|scenario)",
        r"for (a|my) (novel|story|book|movie|research|paper)",
        r"as a thought experiment",
        r"what if you (had no|were not|could)",
    ],

    # ------- Base64 / encoded content ------------------------------------- #
    "base64_detection": [
        r"[A-Za-z0-9+/]{40,}={0,2}",   # Base64 blob
    ],

    # ------- Prompt injection markers ------------------------------------- #
    "prompt_injection": [
        r"<\s*/?system\s*>",
        r"\[INST\]",
        r"<\s*human\s*>",
        r"<\s*assistant\s*>",
        r"###\s*(instruction|system|human|assistant)",
        r"<<SYS>>",
    ],

    # ------- Harmful content requests ------------------------------------- #
    "harmful_content": [
        r"how (to|do I|can I) (make|build|create|synthesize|craft) (a |an )?(bomb|weapon|explosive|poison|drug)",
        r"step[- ]by[- ]step (instructions?|guide) (to|for) (hack|steal|launder|defraud)",
        r"(money[ -]launder|insider[ -]trad|tax[ -]evad|securities fraud)",
        r"(murder|kill|harm|attack) (someone|a person|an individual)",
    ],

    # ------- Manipulation techniques -------------------------------------- #
    "manipulation": [
        r"(sudo|admin|root|god) mode",
        r"developer mode",
        r"training mode",
        r"maintenance mode",
        r"unlock (your|its) (full|true|real|hidden) (potential|mode|capabilities?)",
    ],

    # ------- Format breaking ---------------------------------------------- #
    "format_breaking": [
        r"respond (only |just )?(in|with|using) (json|xml|csv|code|python|javascript)",
        r"output (only|just) (the )?(raw|code|json|xml)",
        r"print the (system|safety|content|original) prompt",
    ],

    # ------- Meta-instructions -------------------------------------------- #
    "meta_instructions": [
        r"your (real|actual|original|true) (purpose|goal|mission|training|instructions?)",
        r"what are your (system |safety )?(instructions?|guidelines?|rules?|constraints?)",
    ],

    # ------- Multi-language attempts -------------------------------------- #
    "multilanguage": [
        r"(répondez|antworte|risposta|responda|reageer) (en|in|auf|en)",
        r"translate (this|it|the following|my request)",
    ],
}

# =========================================================================== #
#  OUTPUT filter patterns (Table 4)
# =========================================================================== #
OUTPUT_PATTERNS = {
    # ------- PII ---------------------------------------------------------- #
    "pii_email": [
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b",
    ],
    "pii_phone": [
        r"\b(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
    ],
    "pii_ssn": [
        r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    ],
    "pii_credit_card": [
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
    ],

    # ------- Violence / threats ------------------------------------------- #
    "violence_threats": [
        r"\b(kill|murder|assassinate|shoot|stab|harm|attack) (you|him|her|them|someone)\b",
        r"(threat(en)?|physical violence|bodily harm)",
    ],

    # ------- Illegal activities ------------------------------------------- #
    "illegal_activities": [
        r"(how to|step[- ]by[- ]step).{0,30}(hack|steal|defraud|launder|evade tax)",
        r"(manufacture|synthesize|produce).{0,30}(meth|cocaine|heroin|fentanyl|firearm)",
    ],

    # ------- Sexual content ----------------------------------------------- #
    "sexual_content": [
        r"\b(nude|naked|explicit sex|pornograph)",
    ],

    # ------- Discriminatory language -------------------------------------- #
    "discriminatory": [
        r"\b(slur|racist|bigot|sexist|homophob|xenophob)",
    ],

    # ------- Medical advice ----------------------------------------------- #
    "medical_advice": [
        r"(take|increase|decrease|inject).{0,20}(mg|milligram|dose|dosage).{0,20}(without|instead of).{0,20}(doctor|physician|prescription)",
    ],

    # ------- Guaranteed financial returns --------------------------------- #
    "guaranteed_returns": [
        r"(guaranteed|risk[ -]free|100% (safe|secure|return|profit))",
        r"(certain|definite) (profit|return|gain)",
    ],

    # ------- Fraud / scam markers ---------------------------------------- #
    "fraud_scam": [
        r"(advance[- ]fee|phishing|ponzi|pyramid scheme|pump[- ]and[- ]dump)",
        r"(wire me|send me|transfer).{0,40}(money|funds|bitcoin|crypto)",
    ],

    # ------- Self-harm --------------------------------------------------- #
    "self_harm": [
        r"(suicide|self[- ]harm|cut yourself|overdose on).{0,40}(method|how|step)",
    ],

    # ------- Step-by-step harmful instructions ---------------------------- #
    "step_by_step_harmful": [
        r"step \d+:.{0,60}(steal|hack|launder|defraud|evade)",
    ],

    # ------- System prompt leakage --------------------------------------- #
    "system_prompt_leakage": [
        r"(my (system|safety) prompt is|here is (the|my) (system|original) prompt)",
        r"(above instruction|original instruction).{0,30}(say|says|state|states|tell)",
    ],
}


# =========================================================================== #
#  RegexFilter class
# =========================================================================== #

class RegexFilter:
    """
    Stateless regex filter for input and output text.
    Returns {"blocked": bool, "matched_pattern": str|None, "pattern_category": str|None}
    """

    @staticmethod
    def _scan(text: str, patterns_dict: dict) -> dict:
        text_lower = text.lower()
        for category, patterns in patterns_dict.items():
            for pattern in patterns:
                m = re.search(pattern, text_lower, re.IGNORECASE | re.DOTALL)
                if m:
                    return {
                        "blocked": True,
                        "matched_pattern": m.group(0),
                        "pattern_category": category,
                    }
        return {"blocked": False, "matched_pattern": None, "pattern_category": None}

    def filter_input(self, text: str) -> dict:
        return self._scan(text, INPUT_PATTERNS)

    def filter_output(self, text: str) -> dict:
        return self._scan(text, OUTPUT_PATTERNS)
