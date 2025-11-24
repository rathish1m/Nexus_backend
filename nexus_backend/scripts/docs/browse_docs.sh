#!/bin/bash
# Documentation Navigator
# Quick access to documentation from terminal

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Documentation root
DOCS_ROOT="./docs"

echo -e "${BOLD}📚 NEXUS TELECOMS - Documentation Navigator${NC}\n"

# Function to open file
open_file() {
    if command -v xdg-open &> /dev/null; then
        xdg-open "$1"
    elif command -v open &> /dev/null; then
        open "$1"
    else
        less "$1"
    fi
}

# Main menu
PS3=$'\n'"${BOLD}Choose an option (number): ${NC}"

options=(
    "📖 Main Documentation Index"
    "🔒 Security & RBAC Documentation"
    "💰 Billing System Documentation"
    "🌍 Translations & i18n Documentation"
    "🏗️ Installation Management Documentation"
    "📋 Survey System Documentation"
    "💳 Payment System Documentation"
    "✨ Features & Fixes Documentation"
    "📘 Integration Guides"
    "📊 Project Summaries"
    "🔍 Validate Documentation Structure"
    "❌ Exit"
)

select opt in "${options[@]}"
do
    case $opt in
        "📖 Main Documentation Index")
            echo -e "\n${GREEN}Opening main documentation index...${NC}"
            open_file "$DOCS_ROOT/INDEX.md"
            break
            ;;
        "🔒 Security & RBAC Documentation")
            echo -e "\n${GREEN}Opening Security & RBAC documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/security/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/security/$filename"
            break
            ;;
        "💰 Billing System Documentation")
            echo -e "\n${GREEN}Opening Billing documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/billing/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/billing/$filename"
            break
            ;;
        "🌍 Translations & i18n Documentation")
            echo -e "\n${GREEN}Opening Translations documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/translations/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/translations/$filename"
            break
            ;;
        "🏗️ Installation Management Documentation")
            echo -e "\n${GREEN}Opening Installation documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/installations/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/installations/$filename"
            break
            ;;
        "📋 Survey System Documentation")
            echo -e "\n${GREEN}Opening Survey documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/surveys/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/surveys/$filename"
            break
            ;;
        "💳 Payment System Documentation")
            echo -e "\n${GREEN}Opening Payment documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/payments/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/payments/$filename"
            break
            ;;
        "✨ Features & Fixes Documentation")
            echo -e "\n${GREEN}Opening Features documentation...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/features/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/features/$filename"
            break
            ;;
        "📘 Integration Guides")
            echo -e "\n${GREEN}Opening Integration guides...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT/guides/"
            echo ""
            read -p "Enter filename (or press Enter for README): " filename
            filename=${filename:-README.md}
            open_file "$DOCS_ROOT/guides/$filename"
            break
            ;;
        "📊 Project Summaries")
            echo -e "\n${GREEN}Opening Project summaries...${NC}"
            echo -e "${BLUE}Available files:${NC}"
            ls -1 "$DOCS_ROOT"/*.md
            echo ""
            read -p "Enter filename: " filename
            open_file "$DOCS_ROOT/$filename"
            break
            ;;
        "🔍 Validate Documentation Structure")
            echo -e "\n${GREEN}Running documentation structure validator...${NC}\n"
            python check_docs_structure.py
            echo ""
            read -p "Press Enter to continue..."
            break
            ;;
        "❌ Exit")
            echo -e "\n${GREEN}Goodbye!${NC}\n"
            break
            ;;
        *)
            echo -e "${RED}Invalid option $REPLY${NC}"
            ;;
    esac
done
