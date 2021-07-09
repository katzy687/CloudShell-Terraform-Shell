# Terraform URLs
TERRAFORM_URL = "https://releases.hashicorp.com/terraform"
TERRAFORM_LATEST_URL = "https://checkpoint-api.hashicorp.com/v1/check/terraform"

# OS types defined by sys.platform
OS_TYPES = {
 'darwin': 'darwin_amd64',
 'linux': 'linux_amd64',
 'win32': 'windows_amd64'
 }

# Log levels
ERROR_LOG_LEVEL = 40
INFO_LOG_LEVEL = 20

# Execution statuses
EXECUTE_STATUS = "EXECUTE_STATUS"
DESTROY_STATUS = "DESTROY_STATUS"
APPLY_PASSED = "APPLY_PASSED"
APPLY_FAILED = "APPLY_FAILED"
PLAN_FAILED = "PLAN_FAILED"
INIT_FAILED = "INIT_FAILED"
DESTROY_FAILED = "DESTROY_FAILED"
DESTROY_PASSED = "DESTROY_PASSED"
NONE = "NONE"

# Command types
INIT = "INIT"
PLAN = "PLAN"
APPLY = "APPLY"
OUTPUT = "OUTPUT"
DESTROY = "DESTROY"
ALLOWED_LOGGING_CMDS = [INIT, PLAN, APPLY, DESTROY]

# Sandbox data keys
TF_WORKING_DIR = "TF_WORKING_DIR"

# CLP models
AZURE2G_MODEL = "Microsoft Azure Cloud Provider 2G"

# Misc
DIRTY_CHARS = r'''
                \x1B  # ESC
                (?:   # 7-bit C1 Fe (except CSI)
                    [@-Z\\-_]
                |     # or [ for CSI, followed by a control sequence
                    \[
                    [0-?]*  # Parameter bytes
                    [ -/]*  # Intermediate bytes
                    [@-~]   # Final byte
                )
            '''


class ATTRIBUTE_NAMES:
    TF_OUTPUTS = "Terraform Outputs"
    TF_SENSIITVE_OUTPUTS = "Terraform Sensitive Outputs"
    TF_INPUTS = "Terraform Inputs"