# Shared by ops/provision_stack.sh (run from ~/aibridge). Source it, then:  load_env FILE
#
# Exports the KEY=VALUE lines of a docker-compose style .env WITHOUT running the file as shell. The scripts used to `set -a; . "$ENVF"`,
# which executes the file: a value with `;`, `$(...)` or a backtick (an API key or token typed on the command line and written
# into the .env) would run, and a value with a space would break the script. Here each line is parsed and exported literally; nothing
# is evaluated. Same results as sourcing for the plain KEY=value files these scripts write (checked against every real stack .env).
#   - blank lines and `# comments` are skipped; an optional leading `export ` is accepted
#   - one pair of matching surrounding quotes is stripped, as the shell and compose do
#   - names that would change how the script itself runs (PATH, LD_*, IFS, BASH_ENV, ...) are refused with a warning
load_env() {
  local f="${1:?load_env FILE}" line k v
  [ -r "$f" ] || { echo "load_env: cannot read $f" >&2; return 1; }
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    k="${BASH_REMATCH[2]}"; v="${BASH_REMATCH[3]}"
    case "$k" in
      PATH|HOME|IFS|ENV|BASH_ENV|SHELL|SHELLOPTS|BASHOPTS|PS4|PROMPT_COMMAND|LD_*|BASH_FUNC_*)
        echo "load_env: ignoring $k in $f (it would change how this script runs)" >&2; continue;;
    esac
    if [[ "$v" =~ ^\"(.*)\"$ ]] || [[ "$v" =~ ^\'(.*)\'$ ]]; then v="${BASH_REMATCH[1]}"; fi
    export "$k=$v"
  done < "$f"
}
