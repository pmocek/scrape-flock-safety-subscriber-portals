#!/bin/bash

# Flock Safety Transparency Portal - Git Scraper
# Fetches agency list and individual agency transparency data
# See https://simonwillison.net/2020/Oct/9/git-scraping/

set -e

# 1. Agency list from haveibeenflocked.com (works, no Cloudflare)
./download.sh 'https://haveibeenflocked.com/news/transparency-portals/'

# 2. Individual Washington agency transparency portals
# Note: These are behind Cloudflare. curl may get blocked.
# Uncomment and test individually once a bypass is working:
#
# WA_AGENCIES=(
#   "piedmont-ca-pd"
# )
# for slug in "${WA_AGENCIES[@]}"; do
#   ./download.sh "https://transparency.flocksafety.com/${slug}"
# done

# 3. Future: Piedmont CA as test case
# ./download.sh 'https://transparency.flocksafety.com/piedmont-ca-pd'