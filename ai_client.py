import os
import json
from typing import Dict, Any

try:
    import openai
except Exception:
    openai = None


def _get_openai_api_key() -> str:
    # Check if we should use external API or built-in recommendations
    use_external_api = os.getenv("USE_EXTERNAL_AI", "false").lower() == "true"
    if not use_external_api:
        return None
    return os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")


def _get_mock_recommendations(climate_label: str, city: str = "") -> Dict[str, Any]:
    """Generate realistic mock recommendations based on climate label for testing/demo purposes."""
    climate = climate_label.lower()
    
    if 'rain' in climate or 'drizzle' in climate or 'thunderstorm' in climate:
        return {
            "irrigation_analysis": {
                "recommendation": "Delay irrigation for 3-5 days. Check soil moisture at 4-6 inch depth before resuming watering schedule.",
                "confidence": 92
            },
            "pest_analysis": {
                "recommendation": "Apply fungicide preventively. Inspect for slug damage and use baits in problem areas. Increase scouting frequency during warm, humid periods.",
                "confidence": 88
            },
            "field_analysis": {
                "recommendation": "Avoid field operations until soil dries. Wait 24-48 hours after rain stops before using heavy machinery to prevent soil compaction.",
                "confidence": 95
            },
            "crop_analysis": {
                "recommendation": "Ensure proper drainage in low areas. Delay nitrogen application until drier conditions. Monitor for signs of waterlogging stress.",
                "confidence": 90
            }
        }
    elif 'winter' in climate or 'snow' in climate or 'cold' in climate:
        return {
            "irrigation_analysis": {
                "recommendation": "Drain and winterize irrigation systems. Protect pipes from freezing. Only water if temperatures consistently above 40°F and soil is dry.",
                "confidence": 95
            },
            "pest_analysis": {
                "recommendation": "Inspect stored grain weekly. Remove crop residue to eliminate pest habitat. Apply dormant oil sprays on fruit trees if temperatures above 40°F.",
                "confidence": 88
            },
            "field_analysis": {
                "recommendation": "Suspend all field operations when ground is frozen or snow-covered. Cover sensitive equipment. Service machinery indoors during downtime.",
                "confidence": 95
            },
            "crop_analysis": {
                "recommendation": "Cover sensitive crops with row covers or mulch before freeze. Protect young trees with trunk wraps. Delay pruning until late winter.",
                "confidence": 92
            }
        }
    elif 'sunny' in climate or 'clear' in climate:
        return {
            "irrigation_analysis": {
                "recommendation": "Increase watering frequency. Irrigate early morning (4-8 AM) or evening to minimize evaporation. Apply 1-1.5 inches per week for most crops.",
                "confidence": 92
            },
            "pest_analysis": {
                "recommendation": "Scout for spider mites and aphids twice weekly. Apply insecticidal soap early if pest threshold reached. Maintain beneficial insect habitat with cover crops.",
                "confidence": 88
            },
            "field_analysis": {
                "recommendation": "Complete spraying, harvesting and planting operations now. Schedule work before 10 AM or after 4 PM. Provide shade and water breaks for workers.",
                "confidence": 95
            },
            "crop_analysis": {
                "recommendation": "Apply shade cloth for heat-sensitive crops. Increase mulch depth to 3-4 inches. Monitor for wilting and apply supplemental water as needed.",
                "confidence": 90
            }
        }
    else:
        return {
            "irrigation_analysis": {
                "recommendation": "Water when top 2 inches of soil is dry. Apply 0.75-1 inch per week. Install moisture sensors for precise scheduling.",
                "confidence": 85
            },
            "pest_analysis": {
                "recommendation": "Scout fields twice weekly. Set up yellow sticky traps to monitor pest populations. Apply treatments only when thresholds are exceeded.",
                "confidence": 82
            },
            "field_analysis": {
                "recommendation": "Proceed with planned field operations. Check 3-day forecast before critical activities. Avoid spraying if rain expected within 24 hours.",
                "confidence": 88
            },
            "crop_analysis": {
                "recommendation": "Apply balanced fertilizer based on soil test results. Monitor crop growth stage weekly. Adjust nitrogen rates according to leaf color and vigor.",
                "confidence": 85
            }
        }


def generate_ai_analysis(climate_label: str, city: str = "") -> Dict[str, Any]:
    """
    Call OpenAI to generate agricultural precaution recommendations for several categories
    based on a simple climate label (e.g. 'rain', 'winter', 'sunny'). Returns a dictionary
    matching the `ai_analysis` shape used by the template, with fields:
      - irrigation_analysis: { recommendation, confidence }
      - pest_analysis: { recommendation, confidence }
      - field_analysis: { recommendation, confidence }
      - crop_analysis: { recommendation, confidence }

    If OpenAI is not available or API key is missing, returns sensible fallback text.
    """
    fallback = _get_mock_recommendations(climate_label, city)  # Use mock recommendations as fallback

    api_key = _get_openai_api_key()
    if not api_key or openai is None:
        return fallback

    # Use the new OpenAI client API (v1.0+)
    # DeepSeek API is OpenAI-compatible, just needs different base_url
    try:
        from openai import OpenAI
        # Check if using DeepSeek API key (starts with 'sk-' but use DeepSeek endpoint)
        if api_key:
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
        else:
            client = OpenAI(api_key=api_key)
    except ImportError:
        # Fallback to old API style
        openai.api_key = api_key
        client = None

    # Construct a concise prompt that asks the model to return strict JSON for parsing
    system_prompt = (
        "You are an expert agricultural advisor. Given a short climate label like 'rain', 'winter', or 'sunny', "
        "produce concise, practical precautionary recommendations for farmers in JSON format. "
        "Return a JSON object with keys: irrigation_analysis, pest_analysis, field_analysis, crop_analysis. "
        "Each value must be an object with 'recommendation' (short text) and 'confidence' (integer 0-100). "
        "Do not include any extra commentary outside the JSON."
    )

    user_prompt = (
        f"City: {city}\nClimate label: {climate_label}\n\n"
        "Provide recommendations focused on practical farm actions (watering, covering crops, delaying operations, pest scouting, etc.)."
    )

    try:
        if client:
            # New API (v1.0+) - works with both OpenAI and DeepSeek
            response = client.chat.completions.create(
                model="deepseek-chat",  # DeepSeek's main model
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            text = response.choices[0].message.content.strip()
        else:
            # Old API (legacy)
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            text = response.choices[0].message.content.strip()

        # Ensure we have JSON only — try to parse the returned text
        # Some models include backticks or markdown, strip common wrappers
        if text.startswith('```'):
            # remove triple backtick code fences
            parts = text.split('```')
            # typical response: ```json\n{...}\n```
            # find the part that looks like JSON
            for part in parts:
                part = part.strip()
                if part.startswith('{'):
                    text = part
                    break

        data = json.loads(text)

        # Normalize values and ensure the shape
        def _normalize(obj):
            rec = obj.get('recommendation', '').strip()
            conf = int(obj.get('confidence', 50)) if obj.get('confidence') is not None else 50
            return {"recommendation": rec, "confidence": conf}

        ai_out = {
            "irrigation_analysis": _normalize(data.get('irrigation_analysis', {})),
            "pest_analysis": _normalize(data.get('pest_analysis', {})),
            "field_analysis": _normalize(data.get('field_analysis', {})),
            "crop_analysis": _normalize(data.get('crop_analysis', {})),
        }
        return ai_out

    except Exception as e:
        # On any error parsing or calling the API return fallback with low confidence
        print(f"AI Client Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return fallback
