#!/bin/bash
# Automatically update the Homebrew tap formula for mcpheroctl
set -e

PACKAGE_NAME="mcpheroctl"
TAP_REPO="arterialist/homebrew-mcpheroctl"
TAP_NAME="arterialist/homebrew-mcpheroctl"
FORMULA_FILE="Formula/mcpheroctl.rb"

echo "🔍 Fetching latest PyPI release info for $PACKAGE_NAME..."

PYPI_JSON=$(curl -sL "https://pypi.org/pypi/$PACKAGE_NAME/json")
LATEST_VERSION=$(echo "$PYPI_JSON" | jq -r '.info.version')

RELEASE_INFO=$(echo "$PYPI_JSON" | jq -r ".releases[\"$LATEST_VERSION\"][] | select(.packagetype == \"sdist\")")
TAR_URL=$(echo "$RELEASE_INFO" | jq -r '.url')
TAR_SHA=$(echo "$RELEASE_INFO" | jq -r '.digests.sha256')

if [ -z "$TAR_URL" ] || [ "$TAR_URL" == "null" ]; then
    echo "❌ Error: Could not extract sdist URL from PyPI for version $LATEST_VERSION."
    exit 1
fi

echo "✅ Found Version: $LATEST_VERSION"
echo "✅ Found SHA256:  $TAR_SHA"

echo "🍺 Tapping $TAP_REPO..."
export HOMEBREW_GITHUB_API_TOKEN="$TAP_GITHUB_TOKEN" 
brew tap "$TAP_NAME" "https://$TAP_GITHUB_TOKEN@github.com/$TAP_REPO.git"

TAP_DIR="$(brew --repo "$TAP_NAME")"
FULL_FORMULA_PATH="$TAP_DIR/$FORMULA_FILE"

echo "📝 Updating $FULL_FORMULA_PATH..."
sed -i.bak -e "s|url \".*\"|url \"$TAR_URL\"|" "$FULL_FORMULA_PATH"
sed -i.bak -e "s|sha256 \".*\"|sha256 \"$TAR_SHA\"|" "$FULL_FORMULA_PATH"
rm -f "$FULL_FORMULA_PATH.bak"

echo "🍺 Running 'brew update-python-resources'..."
brew update-python-resources "$TAP_NAME/$PACKAGE_NAME"

echo "🚀 Committing and pushing to your tap..."
cd "$TAP_DIR"
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

git add "$FORMULA_FILE"
git commit -m "Bump $PACKAGE_NAME to $LATEST_VERSION"
git push origin HEAD:main

echo "🎉 Successfully bumped $PACKAGE_NAME to $LATEST_VERSION in $TAP_REPO!"