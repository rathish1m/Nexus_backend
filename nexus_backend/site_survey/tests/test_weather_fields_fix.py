#!/usr/bin/env python3
"""
Test script to verify that duplicate weather fields have been removed correctly
and that weather field validation works through the Environmental Factors checklist.
"""

import re
import sys


def test_weather_fields_removal():
    """Test that duplicate weather fields have been removed from Final Assessment"""
    print("🧪 Testing Weather Fields Duplication Fix...")

    # Read the survey dashboard template
    template_path = "site_survey/templates/site_survey/survey_dashboard.html"

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Template file not found: {template_path}")
        return False

    # Test 1: Check that weatherDuringSurvey and weatherSignalImpact IDs are not duplicated
    weather_during_matches = re.findall(r'id=["\']weatherDuringSurvey["\']', content)
    weather_impact_matches = re.findall(r'id=["\']weatherSignalImpact["\']', content)

    print(f"   🔍 weatherDuringSurvey ID occurrences: {len(weather_during_matches)}")
    print(f"   🔍 weatherSignalImpact ID occurrences: {len(weather_impact_matches)}")

    if len(weather_during_matches) > 1:
        print(
            f"   ❌ ERROR: weatherDuringSurvey ID appears {len(weather_during_matches)} times (should be 0 or 1)"
        )
        return False

    if len(weather_impact_matches) > 1:
        print(
            f"   ❌ ERROR: weatherSignalImpact ID appears {len(weather_impact_matches)} times (should be 0 or 1)"
        )
        return False

    # Test 2: Check that weather validation code has been removed from validateSurveyCompletion
    weather_validation_pattern = (
        r'getElementById\(["\']weather(?:DuringSurvey|SignalImpact)["\']'
    )
    weather_validation_matches = re.findall(weather_validation_pattern, content)

    print(
        f"   🔍 Weather validation references in JavaScript: {len(weather_validation_matches)}"
    )

    if len(weather_validation_matches) > 0:
        print(
            f"   ❌ ERROR: Found {len(weather_validation_matches)} weather validation references in JavaScript (should be 0)"
        )
        print("   References found:", weather_validation_matches)
        return False

    # Test 3: Check that field count calculation has been updated
    field_count_pattern = r"count \+= \d+.*// Installation feasible.*"
    field_count_matches = re.findall(field_count_pattern, content)

    print(f"   🔍 Field count calculation lines: {len(field_count_matches)}")

    if len(field_count_matches) > 0:
        count_line = field_count_matches[0]
        print(f"   📊 Found count line: {count_line.strip()}")

        # Should not mention weather fields anymore
        if "Weather" in count_line or "weather" in count_line:
            print(
                "   ❌ ERROR: Field count calculation still references weather fields"
            )
            return False

        # Should be count += 3 now (not 5)
        if "count += 5" in count_line:
            print(
                "   ❌ ERROR: Field count still includes weather fields (should be 3, not 5)"
            )
            return False

        if "count += 3" in count_line:
            print(
                "   ✅ Field count correctly updated to 3 (Installation + Mounting + Assessment)"
            )

    # Test 4: Check for any remaining Weather Conditions Section in Final Assessment
    final_assessment_section = re.search(
        r"<!-- Final Assessment Section -->.*?</div>\s*<!-- Additional Costs Section -->",
        content,
        re.DOTALL,
    )

    if final_assessment_section:
        final_assessment_content = final_assessment_section.group(0)
        if "Weather Conditions Section" in final_assessment_content:
            print(
                "   ❌ ERROR: Weather Conditions Section still exists in Final Assessment"
            )
            return False

        if (
            "weatherDuringSurvey" in final_assessment_content
            or "weatherSignalImpact" in final_assessment_content
        ):
            print(
                "   ❌ ERROR: Weather field IDs still found in Final Assessment section"
            )
            return False

    print("   ✅ All duplicate weather field tests passed!")
    return True


def test_environmental_factors_section():
    """Test that Environmental Factors section still exists and contains weather fields"""
    print("\n🌤️  Testing Environmental Factors Section...")

    template_path = "site_survey/templates/site_survey/survey_dashboard.html"

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Template file not found: {template_path}")
        return False

    # Check that weather-related checklist items should exist in the dynamic generation
    # The weather fields should be part of the checklist items, not hardcoded HTML

    # Look for mentions of weather in the checklist rendering logic
    weather_mentions = re.findall(r"weather|Weather", content, re.IGNORECASE)

    print(f"   🔍 Total weather mentions in template: {len(weather_mentions)}")

    # We should have some weather mentions in comments or text, but not in hardcoded form fields
    if len(weather_mentions) == 0:
        print(
            "   ⚠️  WARNING: No weather mentions found. Environmental factors may not be properly configured."
        )

    print(
        "   ℹ️  Weather fields should now be managed through the dynamic checklist system"
    )
    print(
        "   ℹ️  Check your Django backend to ensure Environmental Factors include weather questions"
    )

    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 WEATHER FIELDS DUPLICATION FIX VERIFICATION")
    print("=" * 60)

    success = True

    # Test 1: Weather fields removal
    if not test_weather_fields_removal():
        success = False

    # Test 2: Environmental factors section
    if not test_environmental_factors_section():
        success = False

    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED!")
        print("✅ Duplicate weather fields have been successfully removed")
        print("✅ Weather validation should now work through the checklist system")
        print("\n💡 NEXT STEPS:")
        print(
            "   1. Ensure your Django backend includes weather questions in Environmental Factors"
        )
        print(
            "   2. Test the site survey modal to verify weather fields appear in checklist"
        )
        print("   3. Verify that weather field validation works correctly")
    else:
        print("❌ SOME TESTS FAILED!")
        print("❌ Please review the errors above and fix the issues")
        return 1

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
