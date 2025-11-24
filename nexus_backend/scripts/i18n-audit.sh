#!/bin/bash
#
# i18n-audit.sh - Multilingual Translation Audit Script
#
# This script audits translation files (.po) in the locale/ directory tree,
# providing reproducible statistics and analysis for CI/CD integration.
#
# Features:
# - Counts total lines, msgid entries, and translated messages per language
# - Bilingual output (French/English)
# - Sorted results by language code
# - Exit codes for CI integration
# - JSON output option for automation
# - Colored terminal output
#
# Usage:
#   ./scripts/i18n-audit.sh [options]
#
# Options:
#   -h, --help          Show this help message
#   -j, --json          Output results in JSON format
#   -q, --quiet         Suppress header/footer (for scripting)
#   -e, --english       Force English output
#   -f, --french        Force French output
#   --no-color          Disable colored output
#   --min-coverage N    Set minimum coverage threshold (default: 80)
#
# Exit codes:
#   0: All translations meet coverage threshold
#   1: Some translations below threshold
#   2: No translation files found
#   3: Invalid arguments
#
# Author: Nexus Telecom Development Team
# Version: 1.0.0
# License: MIT

set -euo pipefail

# === CONFIGURATION ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCALE_DIR="$PROJECT_ROOT/locale"
DEFAULT_COVERAGE_THRESHOLD=80
# Base language (source of truth) - should be excluded from coverage checks
BASE_LANGUAGE="en"

# === COLORS ===
if [[ -t 1 ]] && [[ "${NO_COLOR:-}" != "1" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' RESET=''
fi

# === VARIABLES ===
LANGUAGE="auto"
OUTPUT_FORMAT="table"
QUIET_MODE=false
COVERAGE_THRESHOLD=$DEFAULT_COVERAGE_THRESHOLD

# === LOCALIZATION ===
declare -A MESSAGES_FR=(
    ["title"]="🌍 Audit des Traductions Multilingues"
    ["scanning"]="Analyse du répertoire"
    ["found_files"]="fichiers .po trouvés"
    ["no_files"]="Aucun fichier de traduction trouvé dans"
    ["language"]="Langue"
    ["total_lines"]="Lignes totales"
    ["msgid_count"]="Entrées msgid"
    ["translated"]="Traduites"
    ["coverage"]="Couverture"
    ["summary"]="📊 Résumé"
    ["total_languages"]="Langues totales"
    ["avg_coverage"]="Couverture moyenne"
    ["min_coverage"]="Couverture minimale"
    ["max_coverage"]="Couverture maximale"
    ["status_good"]="✅ Toutes les traductions respectent le seuil"
    ["status_warning"]="⚠️  Certaines traductions sous le seuil"
    ["status_error"]="❌ Traductions critiques manquantes"
    ["threshold"]="Seuil de couverture"
    ["recommendation"]="💡 Recommandation: Mise à jour nécessaire pour"
    ["base_language"]="(langue source)"
)

declare -A MESSAGES_EN=(
    ["title"]="🌍 Multilingual Translation Audit"
    ["scanning"]="Scanning directory"
    ["found_files"]=".po files found"
    ["no_files"]="No translation files found in"
    ["language"]="Language"
    ["total_lines"]="Total Lines"
    ["msgid_count"]="msgid Entries"
    ["translated"]="Translated"
    ["coverage"]="Coverage"
    ["summary"]="📊 Summary"
    ["total_languages"]="Total Languages"
    ["avg_coverage"]="Average Coverage"
    ["min_coverage"]="Minimum Coverage"
    ["max_coverage"]="Maximum Coverage"
    ["status_good"]="✅ All translations meet threshold"
    ["status_warning"]="⚠️  Some translations below threshold"
    ["status_error"]="❌ Critical translations missing"
    ["threshold"]="Coverage Threshold"
    ["recommendation"]="💡 Recommendation: Update needed for"
    ["base_language"]="(source language)"
)

# === FUNCTIONS ===

msg() {
    local key="$1"
    case "$LANGUAGE" in
        "fr") echo "${MESSAGES_FR[$key]:-$key}" ;;
        "en") echo "${MESSAGES_EN[$key]:-$key}" ;;
        "auto")
            if [[ "${LANG:-}" =~ ^fr ]]; then
                echo "${MESSAGES_FR[$key]:-$key}"
            else
                echo "${MESSAGES_EN[$key]:-$key}"
            fi
            ;;
    esac
}

show_help() {
    cat << EOF
$(msg "title")

Usage: $0 [options]

Options:
    -h, --help          Show this help message
    -j, --json          Output results in JSON format
    -q, --quiet         Suppress header/footer (for scripting)
    -e, --english       Force English output
    -f, --french        Force French output
    --no-color          Disable colored output
    --min-coverage N    Set minimum coverage threshold (default: $DEFAULT_COVERAGE_THRESHOLD)

Examples:
    $0                          # Basic audit with auto-detected language
    $0 -j                       # JSON output for CI integration
    $0 --french --min-coverage 90  # French output with 90% threshold
    $0 -q --json > audit.json   # Silent JSON export

Exit codes:
    0: All translations meet coverage threshold
    1: Some translations below threshold
    2: No translation files found
    3: Invalid arguments
EOF
}

log_info() {
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${BLUE}ℹ️  $*${RESET}" >&2
    fi
}

log_warning() {
    echo -e "${YELLOW}⚠️  $*${RESET}" >&2
}

log_error() {
    echo -e "${RED}❌ $*${RESET}" >&2
}

log_success() {
    if [[ "$QUIET_MODE" != "true" ]]; then
        echo -e "${GREEN}✅ $*${RESET}" >&2
    fi
}

analyze_po_file() {
    local po_file="$1"
    local lang_code="$2"  # Add language code parameter
    local total_lines
    local msgid_count
    local translated_count
    local coverage

    total_lines=$(wc -l < "$po_file")
    msgid_count=$(grep -c "^msgid " "$po_file" 2>/dev/null || echo "0")

    # Ensure msgid_count is a number
    if [[ ! "$msgid_count" =~ ^[0-9]+$ ]]; then
        msgid_count=0
    fi

    # Special handling for base language (source of truth)
    if [[ "$lang_code" == "$BASE_LANGUAGE" ]]; then
        # Base language is considered 100% complete by definition
        # since it contains the source strings
        translated_count=$msgid_count
        coverage=100
    else
        # Count non-empty msgstr entries (translated)
        # Look for msgstr with actual content (not empty quotes)
        translated_count=$(grep -E "^msgstr \"[^\"]+\"" "$po_file" 2>/dev/null | wc -l)
        if [[ -z "$translated_count" ]]; then
            translated_count=0
        fi

        if [[ $msgid_count -gt 0 ]]; then
            coverage=$(( (translated_count * 100) / msgid_count ))
        else
            coverage=0
        fi
    fi

    echo "$total_lines:$msgid_count:$translated_count:$coverage"
}

format_coverage() {
    local coverage="$1"
    if [[ $coverage -ge $COVERAGE_THRESHOLD ]]; then
        echo -e "${GREEN}${coverage}%${RESET}"
    elif [[ $coverage -ge 50 ]]; then
        echo -e "${YELLOW}${coverage}%${RESET}"
    else
        echo -e "${RED}${coverage}%${RESET}"
    fi
}

generate_json_output() {
    local -n results_ref=$1
    local total_langs="$2"
    local avg_coverage="$3"
    local min_coverage="$4"
    local max_coverage="$5"
    local below_threshold="$6"

    echo "{"
    echo "  \"audit_timestamp\": \"$(date -Iseconds)\","
    echo "  \"project_root\": \"$PROJECT_ROOT\","
    echo "  \"coverage_threshold\": $COVERAGE_THRESHOLD,"
    echo "  \"summary\": {"
    echo "    \"total_languages\": $total_langs,"
    echo "    \"average_coverage\": $avg_coverage,"
    echo "    \"minimum_coverage\": $min_coverage,"
    echo "    \"maximum_coverage\": $max_coverage,"
    echo "    \"languages_below_threshold\": $below_threshold"
    echo "  },"
    echo "  \"languages\": ["

    local first=true
    for lang in "${!results_ref[@]}"; do
        if [[ "$first" != "true" ]]; then
            echo ","
        fi
        first=false

        IFS=':' read -r total_lines msgid_count translated_count coverage <<< "${results_ref[$lang]}"
        echo "    {"
        echo "      \"code\": \"$lang\","
        echo "      \"total_lines\": $total_lines,"
        echo "      \"msgid_entries\": $msgid_count,"
        echo "      \"translated_entries\": $translated_count,"
        echo "      \"coverage_percentage\": $coverage,"
        echo -n "      \"meets_threshold\": "
        if [[ $coverage -ge $COVERAGE_THRESHOLD ]]; then
            echo "true"
        else
            echo "false"
        fi
        echo -n "    }"
    done
    echo ""
    echo "  ]"
    echo "}"
}

# === MAIN SCRIPT ===

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -j|--json)
            OUTPUT_FORMAT="json"
            shift
            ;;
        -q|--quiet)
            QUIET_MODE=true
            shift
            ;;
        -e|--english)
            LANGUAGE="en"
            shift
            ;;
        -f|--french)
            LANGUAGE="fr"
            shift
            ;;
        --no-color)
            NO_COLOR=1
            RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' RESET=''
            shift
            ;;
        --min-coverage)
            if [[ -n "${2:-}" ]] && [[ "$2" =~ ^[0-9]+$ ]] && [[ "$2" -ge 0 ]] && [[ "$2" -le 100 ]]; then
                COVERAGE_THRESHOLD="$2"
                shift 2
            else
                log_error "Invalid coverage threshold. Must be a number between 0 and 100."
                exit 3
            fi
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 3
            ;;
    esac
done

# Check if locale directory exists
if [[ ! -d "$LOCALE_DIR" ]]; then
    log_error "$(msg "no_files") $LOCALE_DIR"
    exit 2
fi

# Find all .po files
declare -A results
po_files=()
while IFS= read -r -d '' file; do
    po_files+=("$file")
done < <(find "$LOCALE_DIR" -name "*.po" -type f -print0 2>/dev/null)

if [[ ${#po_files[@]} -eq 0 ]]; then
    log_error "$(msg "no_files") $LOCALE_DIR"
    exit 2
fi

if [[ "$OUTPUT_FORMAT" == "table" ]] && [[ "$QUIET_MODE" != "true" ]]; then
    echo -e "${BOLD}$(msg "title")${RESET}"
    echo -e "${CYAN}$(msg "scanning"): $LOCALE_DIR${RESET}"
    echo -e "${CYAN}${#po_files[@]} $(msg "found_files")${RESET}"
    echo ""
fi

# Analyze each .po file
for po_file in "${po_files[@]}"; do
    # Extract language code from path (e.g., locale/fr/LC_MESSAGES/django.po -> fr)
    lang_code=$(echo "$po_file" | sed -n 's|.*/locale/\([^/]*\)/.*|\1|p')

    if [[ -z "$lang_code" ]]; then
        log_warning "Could not extract language code from: $po_file"
        continue
    fi

    analysis=$(analyze_po_file "$po_file" "$lang_code")
    results["$lang_code"]="$analysis"
done

# Calculate statistics
total_langs=${#results[@]}
total_coverage=0
min_coverage=100
max_coverage=0
below_threshold=0

for lang in "${!results[@]}"; do
    IFS=':' read -r _ _ _ coverage <<< "${results[$lang]}"
    total_coverage=$((total_coverage + coverage))

    if [[ $coverage -lt $min_coverage ]]; then
        min_coverage=$coverage
    fi

    if [[ $coverage -gt $max_coverage ]]; then
        max_coverage=$coverage
    fi

    if [[ $coverage -lt $COVERAGE_THRESHOLD ]]; then
        below_threshold=$((below_threshold + 1))
    fi
done

avg_coverage=$((total_coverage / total_langs))

# Output results
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    generate_json_output results "$total_langs" "$avg_coverage" "$min_coverage" "$max_coverage" "$below_threshold"
else
    # Table format
    printf "${BOLD}%-12s %12s %12s %12s %12s${RESET}\n" \
        "$(msg "language")" \
        "$(msg "total_lines")" \
        "$(msg "msgid_count")" \
        "$(msg "translated")" \
        "$(msg "coverage")"

    echo "$(printf '%.0s─' {1..70})"

    # Sort languages alphabetically
    for lang in $(printf '%s\n' "${!results[@]}" | sort); do
        IFS=':' read -r total_lines msgid_count translated_count coverage <<< "${results[$lang]}"

        # Add indicator for base language
        lang_display="$lang"
        if [[ "$lang" == "$BASE_LANGUAGE" ]]; then
            lang_display="$lang $(msg "base_language")"
        fi

        printf "%-12s %12d %12d %12d %12s\n" \
            "$lang_display" \
            "$total_lines" \
            "$msgid_count" \
            "$translated_count" \
            "$(format_coverage "$coverage")"
    done

    if [[ "$QUIET_MODE" != "true" ]]; then
        echo ""
        echo -e "${BOLD}$(msg "summary")${RESET}"
        echo "$(printf '%.0s─' {1..30})"
        echo "$(msg "total_languages"): $total_langs"
        echo "$(msg "avg_coverage"): $(format_coverage "$avg_coverage")"
        echo "$(msg "min_coverage"): $(format_coverage "$min_coverage")"
        echo "$(msg "max_coverage"): $(format_coverage "$max_coverage")"
        echo "$(msg "threshold"): ${COVERAGE_THRESHOLD}%"
        echo ""

        # Status message
        if [[ $below_threshold -eq 0 ]]; then
            log_success "$(msg "status_good") (${COVERAGE_THRESHOLD}%)"
        elif [[ $min_coverage -ge 50 ]]; then
            log_warning "$(msg "status_warning") ($below_threshold/$total_langs)"
        else
            log_error "$(msg "status_error")"
        fi

        # Recommendations
        if [[ $below_threshold -gt 0 ]]; then
            echo ""
            echo -e "${CYAN}$(msg "recommendation"):${RESET}"
            for lang in $(printf '%s\n' "${!results[@]}" | sort); do
                IFS=':' read -r _ _ _ coverage <<< "${results[$lang]}"
                if [[ $coverage -lt $COVERAGE_THRESHOLD ]]; then
                    echo "  • $lang (${coverage}%)"
                fi
            done
        fi
    fi
fi

# Exit with appropriate code
if [[ $below_threshold -eq 0 ]]; then
    exit 0
else
    exit 1
fi
