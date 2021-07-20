import json
import os
from datetime import datetime
from subprocess import check_output, STDOUT, CalledProcessError
from cloudshell.logging.qs_logger import _create_logger

from cloudshell.iac.terraform.constants import ERROR_LOG_LEVEL, INFO_LOG_LEVEL, EXECUTE_STATUS, APPLY_PASSED, \
    PLAN_FAILED, INIT_FAILED, \
    DESTROY_STATUS, DESTROY_FAILED, APPLY_FAILED, DESTROY_PASSED, INIT, DESTROY, PLAN, OUTPUT, APPLY, \
    ALLOWED_LOGGING_CMDS, ATTRIBUTE_NAMES
from cloudshell.iac.terraform.models.shell_helper import ShellHelperObject
from cloudshell.iac.terraform.models.exceptions import TerraformExecutionError
from cloudshell.iac.terraform.services.backend_handler import BackendHandler
from cloudshell.iac.terraform.services.input_output_service import InputOutputService
from cloudshell.iac.terraform.services.sandox_data import SandboxDataHandler
from cloudshell.iac.terraform.services.string_cleaner import StringCleaner
from cloudshell.iac.terraform.tagging.tag_terraform_resources import start_tagging_terraform_resources
from cloudshell.iac.terraform.tagging.tags import TagsManager


class TfProcExec(object):
    def __init__(self, shell_helper: ShellHelperObject, sb_data_handler: SandboxDataHandler,
                 input_output_service: InputOutputService, reservation):
        self._shell_helper = shell_helper
        self._sb_data_handler = sb_data_handler
        self._input_output_service = input_output_service
        self._tf_workingdir = sb_data_handler.get_tf_working_dir()
        self._reservation = reservation

        dt = datetime.now().strftime("%d_%m_%y-%H_%M_%S")
        self._exec_output_log = _create_logger(
            log_group=shell_helper.sandbox_id, log_category="QS", log_file_prefix=f"TF_EXEC_LOG_{dt}"
        )

    def init_terraform(self):
        self._shell_helper.logger.info("Performing Terraform Init")
        self._shell_helper.sandbox_messages.write_message("running Terraform Init...")
        backend_config_vars = self._init_backend_config()
        vars = ["init", "-no-color"]
        for key in backend_config_vars.keys():
            vars.append(f'-backend-config={key}={backend_config_vars[key]}')
        try:
            self._set_service_status("Progress 10", "Executing Terraform Init...")
            self._run_tf_proc_with_command(vars, INIT)
            self._set_service_status("Progress 30", "Init Passed")
        except Exception as e:
            self._sb_data_handler.set_status(EXECUTE_STATUS, INIT_FAILED)
            self._set_service_status("Error", "Init Failed")
            raise

    def destroy_terraform(self):
        self._shell_helper.logger.info("Performing Terraform Destroy")
        self._shell_helper.sandbox_messages.write_message("running Terraform Destroy...")
        cmd = ["destroy", "-auto-approve", "-no-color"]

        # get variables from attributes that should be mapped to TF variables
        tf_vars = self._input_output_service.get_variables_from_var_attributes()
        # get any additional TF variables from "Terraform Inputs" variable
        tf_vars.extend(self._input_output_service.get_variables_from_terraform_input_attribute())

        # add all TF variables to command
        for tf_var in tf_vars:
            cmd.append("-var")
            cmd.append(f"{tf_var.name}={tf_var.value}")

        try:
            self._set_service_status("Progress 50", "Executing Terraform Destroy...")
            self._run_tf_proc_with_command(cmd, DESTROY)
            self._sb_data_handler.set_status(DESTROY_STATUS, DESTROY_PASSED)
            self._set_service_status("Offline", "Destroy Passed")

        except Exception as e:
            self._sb_data_handler.set_status(DESTROY_STATUS, DESTROY_FAILED)
            self._set_service_status("Error", "Destroy Failed")
            raise

    def tag_terraform(self) -> None:

        if not self._input_output_service.get_apply_tag_attribute():
            self._shell_helper.logger.info("Skipping Adding Tags to Terraform Resources")
            self._shell_helper.sandbox_messages.write_message("apply tags is false, skipping adding tags...")
            return

        self._shell_helper.logger.info("Adding Tags to Terraform Resources")
        self._shell_helper.sandbox_messages.write_message("apply tags is true, generating tags...")

        # get variables from attributes that should be mapped to TF variables
        tf_vars = self._input_output_service.get_variables_from_var_attributes()
        # get any additional TF variables from "Terraform Inputs" variable
        tf_vars.extend(self._input_output_service.get_variables_from_terraform_input_attribute())

        inputs_dict = dict()

        # add all TF variables to command
        for tf_var in tf_vars:
            inputs_dict[tf_var.name] = tf_var.value

        default_tags = TagsManager(self._reservation)
        default_tags_dict: dict = default_tags.get_default_tags()

        custom_tags_inputs = self._input_output_service.get_variables_from_custom_tags_attribute()

        tags_dict = {**custom_tags_inputs, **default_tags_dict}

        if len(tags_dict) > 50:
            raise ValueError("AWS and Azure have a limit of 50 tags per resource, you have " + str(len(tags_dict)))

        self._shell_helper.logger.info(self._tf_workingdir)
        self._shell_helper.logger.info(tags_dict)

        start_tagging_terraform_resources(self._tf_workingdir, self._shell_helper.logger, tags_dict, inputs_dict)

    def plan_terraform(self) -> None:
        self._shell_helper.logger.info("Running Terraform Plan")
        self._shell_helper.sandbox_messages.write_message("generating Terraform Plan...")

        cmd = ["plan", "-out", "planfile", "-input=false", "-no-color"]

        # get variables from attributes that should be mapped to TF variables
        tf_vars = self._input_output_service.get_variables_from_var_attributes()
        # get any additional TF variables from "Terraform Inputs" variable
        tf_vars.extend(self._input_output_service.get_variables_from_terraform_input_attribute())

        # add all TF variables to command
        for tf_var in tf_vars:
            cmd.append("-var")
            cmd.append(f"{tf_var.name}={tf_var.value}")

        try:
            self._set_service_status("Progress 40", "Executing Terraform Plan...")
            self._run_tf_proc_with_command(cmd, PLAN)
            self._set_service_status("Progress 60", "Plan Passed")
        except Exception:
            self._sb_data_handler.set_status(EXECUTE_STATUS, PLAN_FAILED)
            self._set_service_status("Error", "Plan Failed")
            raise

    def apply_terraform(self):
        self._shell_helper.logger.info("Running Terraform Apply")
        self._shell_helper.sandbox_messages.write_message("executing Terraform Apply...")
        cmd = ["apply", "--auto-approve", "-no-color", "planfile"]

        try:
            self._set_service_status("Progress 70", "Executing Terraform Apply...")
            self._run_tf_proc_with_command(cmd, APPLY)
            self._sb_data_handler.set_status(EXECUTE_STATUS, APPLY_PASSED)
            self._set_service_status("Online", "Apply Passed")
        except Exception as e:
            self._sb_data_handler.set_status(EXECUTE_STATUS, APPLY_FAILED)
            self._set_service_status("Error", "Apply Failed")
            raise

    def save_terraform_outputs(self):
        try:
            self._shell_helper.logger.info("Running 'terraform output -json'")

            # get all TF outputs in json format
            cmd = ["output", "-json"]
            tf_exec_output = self._run_tf_proc_with_command(cmd, OUTPUT, write_to_log=False)
            unparsed_output_json = json.loads(tf_exec_output)

            self._input_output_service.parse_and_save_outputs(unparsed_output_json)

        except Exception as e:
            self._shell_helper.logger.error(f"Error occurred while trying to parse Terraform outputs -> {str(e)}")
            raise

    def can_execute_run(self) -> bool:
        execute_status = self._sb_data_handler.get_status(EXECUTE_STATUS)
        destroy_status = self._sb_data_handler.get_status(DESTROY_STATUS)
        if execute_status in [APPLY_FAILED]:
            return False
        if destroy_status in [DESTROY_FAILED] and execute_status == APPLY_PASSED:
            return False
        return True

    def can_destroy_run(self) -> bool:
        execute_status = self._sb_data_handler.get_status(EXECUTE_STATUS)
        if execute_status not in [APPLY_PASSED, APPLY_FAILED]:
            return False
        return True

    def _run_tf_proc_with_command(self, cmd: list, command: str, write_to_log: bool = True) -> str:
        tform_command = [f"{os.path.join(self._tf_workingdir, 'terraform.exe')}"]
        tform_command.extend(cmd)

        try:
            output = check_output(tform_command, shell=True, cwd=self._tf_workingdir, stderr=STDOUT).decode('utf-8')

            clean_output = StringCleaner.get_clean_string(output)
            if write_to_log:
                self._write_to_exec_log(command, clean_output, INFO_LOG_LEVEL)
            return output

        except CalledProcessError as e:
            clean_output = StringCleaner.get_clean_string(e.output.decode('utf-8'))
            self._shell_helper.logger.error(
                f"Error occurred while trying to execute Terraform | Output = {clean_output}"
            )
            if command in ALLOWED_LOGGING_CMDS:
                self._write_to_exec_log(command, clean_output, ERROR_LOG_LEVEL)
            raise TerraformExecutionError("Error during Terraform Plan. For more information please look at the logs.",
                                          clean_output)
        except Exception as e:
            clean_output = StringCleaner.get_clean_string(str(e))
            self._shell_helper.logger.error(f"Error Running Terraform plan {clean_output}")
            raise TerraformExecutionError("Error during Terraform Plan. For more information please look at the logs.")

    def _write_to_exec_log(self, command: str, log_data: str, log_level: int) -> None:
        clean_output = StringCleaner.get_clean_string(log_data)
        self._exec_output_log.log(
            log_level,
            f"-------------------------------------------------=< {command} START "
            f">=-------------------------------------------------\n"
        )
        self._exec_output_log.log(log_level, clean_output)
        self._exec_output_log.log(
            log_level,
            f"-------------------------------------------------=< {command} END "
            f">=---------------------------------------------------\n"
        )

    def _set_service_status(self, status: str, description: str):
        self._shell_helper.live_status_updater.set_service_live_status(
            self._shell_helper.tf_service.name,
            status,
            description
        )

    def _init_backend_config(self):
        backend_attribute_name = f"{self._shell_helper.tf_service.cloudshell_model_name}.Remote State Provider"

        if backend_attribute_name in self._shell_helper.tf_service.attributes:
            remote_state_provider = self._shell_helper.tf_service.attributes[backend_attribute_name]
            if remote_state_provider:
                backend_handler = BackendHandler(
                    self._shell_helper.logger,
                    self._shell_helper.api,
                    remote_state_provider,
                    self._tf_workingdir,
                    self._shell_helper.sandbox_id,
                    self._sb_data_handler._get_tf_uuid()
                )
                backend_handler.generate_backend_cfg_file()
                return backend_handler.get_backend_secret_vars()
        else:
            return ""
