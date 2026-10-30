#!/usr/bin/env bash
# setup.sh - create one-word command shims for the db_* submodules (Linux/macOS).
#
# After running this script you can type, from any directory:
#   db_split <args>        (instead of: python3 -m db_split <args>)
#   db_copy / db_append / db_assign / db_recycled / db_analysis work the same.
#
# What it does:
#   1. Creates a "bin" folder next to this script.
#   2. Writes one small bash shim per submodule into that folder.
#   3. Symlinks them into ~/.local/bin (creating it if needed) so they
#      land on PATH in most distributions.
#
# Usage (run once, from the project root):
#   bash setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$ROOT/bin"
mkdir -p "$BIN"

MODULES="db_recycled db_split db_copy db_append db_assign db_analysis"

for m in $MODULES; do
    shim="$BIN/$m"
    cat > "$shim" <<EOF
#!/usr/bin/env bash
# One-word shim for: python3 -m $m
SELF="\$(readlink -f "\${BASH_SOURCE[0]}")"
PKG_ROOT="\$(cd "\$(dirname "\$SELF")/.." && pwd)"
export PYTHONPATH="\$PKG_ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m $m "\$@"
EOF
    chmod +x "$shim"
    echo "created $shim"
done

LINK_DIR="$HOME/.local/bin"
mkdir -p "$LINK_DIR"
for m in $MODULES; do
    ln -sf "$BIN/$m" "$LINK_DIR/$m"
done
echo "linked into $LINK_DIR"

case ":$PATH:" in
    *":$LINK_DIR:"*) ;;
    *)
        echo "note: $LINK_DIR is not on your PATH in this shell."
        echo "      add this line to ~/.bashrc (then open a new shell):"
        echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo ""
echo "Done. Try one:"
for m in $MODULES; do
    echo "    $m --help"
done
