#!/bin/bash
# Load test environment variables and run pytest

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Loading test environment variables...${NC}"

# Check if .env.test exists
if [ ! -f .env.test ]; then
    echo -e "${RED}Error: .env.test file not found!${NC}"
    echo -e "${YELLOW}Creating .env.test from .env.example...${NC}"

    if [ -f .env.example ]; then
        cp .env.example .env.test
        echo -e "${GREEN}.env.test created. Please configure it for testing.${NC}"
    else
        echo -e "${RED}Error: .env.example not found either!${NC}"
        exit 1
    fi
fi

# Export environment variables from .env.test
set -a
source .env.test
set +a

echo -e "${GREEN}Environment variables loaded successfully!${NC}"
echo -e "${YELLOW}Running pytest...${NC}"
echo ""

# Run pytest with all arguments passed to this script
exec "$@"
