#!/usr/bin/env bash
#
# DogTag workshop bootstrap. Run on a fresh Amazon Linux 2023 EC2 instance
# (e.g. via SSM Session Manager) to install git + pip, clone the repo
# into $HOME/dog-tag, and install the Python dependencies.
#
# Bootstrap from zero (the script lives inside the repo, so participants
# fetch it directly from GitHub the first time):
#
#   curl -sO https://raw.githubusercontent.com/m-dresser/dog-tag/main/setup.sh
#   bash setup.sh

set -euo pipefail

REPO_URL="https://github.com/m-dresser/dog-tag.git"
REPO_DIR="$HOME/dog-tag"

echo "==> Installing git and pip"
sudo dnf install -y git python3-pip

if [ -d "$REPO_DIR/.git" ]; then
  echo "==> $REPO_DIR already exists, skipping clone"
else
  echo "==> Cloning $REPO_URL into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "==> Installing Python dependencies"
pip3 install -r "$REPO_DIR/requirements.txt"

echo
echo "Done. Next steps:"
echo "  cd $REPO_DIR"
echo "  python3 app.py"
