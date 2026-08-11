from __future__ import annotations

import posixpath

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.operational_manifests_v4 import (
    CHRONYD_COMMAND_PROXY_PROFILE,
    CHRONYD_FIXED_ENVIRONMENT_SHA256,
    CHRONYD_LAUNCH_PROFILE,
    CHRONYD_SUPERVISOR_PROFILE,
    ChronydLaunchPolicyV48B,
)


def make_test_chronyd_launch_policy_v48b(
    *, read_only_api_socket_path: str
) -> ChronydLaunchPolicyV48B:
    supervisor_socket_directory_path = posixpath.dirname(read_only_api_socket_path)
    runtime_directory_path = posixpath.dirname(supervisor_socket_directory_path)
    chronyd_socket_directory_path = f"{runtime_directory_path}/chronyd"
    return ChronydLaunchPolicyV48B(
        launch_profile=CHRONYD_LAUNCH_PROFILE,
        supervisor_profile=CHRONYD_SUPERVISOR_PROFILE,
        command_proxy_profile=CHRONYD_COMMAND_PROXY_PROFILE,
        systemd_unit_name="riskyieldmm-chronyd.service",
        systemd_unit_path="/etc/systemd/system/riskyieldmm-chronyd.service",
        systemd_unit_sha256=sha256_digest({"fixture": "chronyd-unit"}),
        chronyd_executable_path="/usr/sbin/chronyd",
        chronyd_executable_sha256=sha256_digest({"fixture": "chronyd"}),
        effective_config_sha256=sha256_digest({"fixture": "chronyd-effective-config"}),
        printed_config_sha256=sha256_digest({"fixture": "chronyd-printed-config"}),
        fixed_environment_sha256=CHRONYD_FIXED_ENVIRONMENT_SHA256,
        runtime_directory_path=runtime_directory_path,
        chronyd_socket_directory_path=chronyd_socket_directory_path,
        supervisor_socket_directory_path=supervisor_socket_directory_path,
        real_command_socket_path=(f"{chronyd_socket_directory_path}/command.sock"),
        notify_socket_path=f"{supervisor_socket_directory_path}/notify.sock",
        read_only_api_socket_path=read_only_api_socket_path,
        post_drop_user_name="chrony",
        post_drop_uid=102,
        post_drop_gid=102,
        lsm_profile="APPARMOR_RISKYIELDMM_CHRONYD_V1",
        ready_timeout_milliseconds=10_000,
        maximum_datagram_bytes=65_536,
    )


__all__ = ["make_test_chronyd_launch_policy_v48b"]
