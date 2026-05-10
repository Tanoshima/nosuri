#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.config/nix"
if ! grep -q '^experimental-features' "$HOME/.config/nix/nix.conf" 2>/dev/null; then
  echo 'experimental-features = nix-command flakes' >> "$HOME/.config/nix/nix.conf"
fi

if [ ! -e "$HOME/.nix-profile/share/nix-direnv/direnvrc" ]; then
  nix profile install nixpkgs#nix-direnv
fi

mkdir -p "$HOME/.config/direnv"
cat > "$HOME/.config/direnv/direnvrc" <<'EOF'
source "$HOME/.nix-profile/share/nix-direnv/direnvrc"
EOF

if ! grep -qxF 'eval "$(direnv hook zsh)"' "$HOME/.zshrc" 2>/dev/null; then
  echo 'eval "$(direnv hook zsh)"' >> "$HOME/.zshrc"
fi

if [ -d /workspaces/nosuri ]; then
  direnv allow /workspaces/nosuri
fi
