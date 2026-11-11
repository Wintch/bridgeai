# Shared by ops/privacy_scan.sh and ops/make_jobfinder_bundle.sh (source it).
# private_pattern FILE -> prints one PCRE alternation built from the left sides of a git-filter-repo replacements file:
#   regex:<re>==>x   used as a regex (a leading (?i) is dropped: callers match case-insensitively anyway)
#   glob:<g>==>x     glob turned into a regex (* and ? only)
#   literal:<s>==>x  and plain  <s>==>x  or  <s>   escaped, because they are literal strings
# Prints nothing for an empty list. Returns 1 when FILE is missing (the caller decides if that is fatal).
_pp_escape() { sed -e 's/[][\\.^$*+?(){}|\/#&-]/\\&/g'; }
private_pattern() {
  local file="$1" line left out=""
  [ -f "$file" ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    left="${line%%==>*}"
    case "$left" in
      regex:*)   left="${left#regex:}"; left="${left//\(\?i\)/}"; [ -n "$left" ] && left="(?:$left)" ;;
      glob:*)    left="${left#glob:}"
                 left=$(printf '%s' "$left" | _pp_escape | sed -e 's/\\[*]/.*/g' -e 's/\\[?]/./g') ;;
      literal:*) left=$(printf '%s' "${left#literal:}" | _pp_escape) ;;
      *)         left=$(printf '%s' "$left" | _pp_escape) ;;
    esac
    [ -n "$left" ] && out+="${out:+|}$left"
  done < "$file"
  printf '%s' "$out"
}
