# ======================================================================
# CGI AI Exchange CODEOWNERS Template
# ----------------------------------------------------------------------
# This file assigns individual owners to specific parts of the repository.
# Replace @username with actual GitHub usernames.
#
# Format:
#   Each line: <file pattern> <one or more owners>
#   Owners must be GitHub usernames with '@' prefix.
#   The last matching pattern takes precedence.
# ======================================================================

# Default ownership for the entire repository
*               @sivakumar-rangaiah

# Example: Assign specific owners for directories
/docs/          @sivakumar-rangaiah
/notebooks/     @sivakumar-rangaiah
/src/           @sivakumar-rangaiah
/tests/         @sivakumar-rangaiah

# Example: Assign a maintainer for configuration files
/configs/       @sivakumar-rangaiah

# Example: Shared ownership for workflows and automation
/.github/       @sivakumar-rangaiah

# Assign documentation-related files
*.md            @sivakumar-rangaiah

# Assign YAML or configuration scripts
*.yaml          @sivakumar-rangaiah

# ======================================================================
# Notes:
# - Ensure all listed usernames exist in this organization.
# - The file must be committed to the 'main' branch.
# - Pull Requests affecting any path here require at least one review
#   from the listed owners before merging.
# ======================================================================
