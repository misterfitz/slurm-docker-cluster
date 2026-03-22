"""Tests for the simulate module — data structures, config generation, CLI."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from slurm_playground.simulate import (
    ACCOUNTS,
    PROFILE_JOBS,
    QOS_TIERS,
    QOS_WEIGHTS,
    get_all_users,
    _compress_node_range,
    generate_simulation_slurm_conf,
    simulate,
)


# ── Data structure invariants ───────────────────────────────────────


class TestAccountTopology:
    def test_50_users(self):
        assert len(get_all_users()) == 50

    def test_15_accounts(self):
        assert len(ACCOUNTS) == 15

    def test_no_duplicate_users(self):
        users = get_all_users()
        assert len(users) == len(set(users))

    def test_all_accounts_have_users(self):
        for acct in ACCOUNTS:
            assert len(acct["users"]) > 0, f"Account {acct['name']} has no users"

    def test_all_accounts_have_valid_profile(self):
        for acct in ACCOUNTS:
            assert acct["profile"] in PROFILE_JOBS, (
                f"Account {acct['name']} has invalid profile {acct['profile']}"
            )

    def test_all_accounts_have_positive_shares(self):
        for acct in ACCOUNTS:
            assert acct["shares"] > 0, f"Account {acct['name']} has zero shares"

    def test_user_naming_convention(self):
        for user in get_all_users():
            assert user.startswith("user"), f"User {user} doesn't follow naming convention"
            num = user[4:]
            assert num.isdigit(), f"User {user} doesn't have numeric suffix"
            assert 1 <= int(num) <= 50

    def test_users_sequential(self):
        """All user01-user50 are present."""
        users = set(get_all_users())
        for i in range(1, 51):
            assert f"user{i:02d}" in users, f"user{i:02d} is missing"


class TestQOSConfig:
    def test_4_tiers(self):
        assert len(QOS_TIERS) == 4

    def test_tier_names(self):
        names = {q["name"] for q in QOS_TIERS}
        assert names == {"low", "normal", "high", "urgent"}

    def test_ascending_priority(self):
        priorities = [q["priority"] for q in QOS_TIERS]
        assert priorities == sorted(priorities)

    def test_weights_match_tiers(self):
        tier_names = {q["name"] for q in QOS_TIERS}
        weight_names = set(QOS_WEIGHTS.keys())
        assert tier_names == weight_names

    def test_weights_sum_to_100(self):
        assert sum(QOS_WEIGHTS.values()) == 100

    def test_normal_is_dominant(self):
        assert QOS_WEIGHTS["normal"] > sum(
            v for k, v in QOS_WEIGHTS.items() if k != "normal"
        )


class TestProfileJobs:
    def test_all_profiles_have_ranges(self):
        for profile, (lo, hi) in PROFILE_JOBS.items():
            assert lo > 0, f"Profile {profile} has zero low bound"
            assert hi >= lo, f"Profile {profile} has hi < lo"

    def test_heavy_submits_most(self):
        heavy_avg = sum(PROFILE_JOBS["heavy"]) / 2
        medium_avg = sum(PROFILE_JOBS["medium"]) / 2
        light_avg = sum(PROFILE_JOBS["light"]) / 2
        assert heavy_avg > medium_avg > light_avg

    def test_estimated_total_around_30k(self):
        """The default config should produce roughly 25k-35k jobs."""
        total = 0
        for acct in ACCOUNTS:
            lo, hi = PROFILE_JOBS[acct["profile"]]
            avg = (lo + hi) / 2
            total += avg * len(acct["users"])
        assert 20000 <= total <= 40000, f"Estimated total {total} outside expected range"


# ── Node range compression ──────────────────────────────────────────


class TestCompressNodeRange:
    def test_single(self):
        assert _compress_node_range(["c1"]) == "c1"

    def test_range(self):
        assert _compress_node_range(["c1", "c2", "c3"]) == "c[1-3]"

    def test_unsorted_input(self):
        assert _compress_node_range(["c3", "c1", "c2"]) == "c[1-3]"

    def test_mixed_prefixes(self):
        result = _compress_node_range(["c1", "c2", "hm1", "hm2"])
        assert "c[1-2]" in result
        assert "hm[1-2]" in result

    def test_empty(self):
        assert _compress_node_range([]) == ""


# ── slurm.conf generation ──────────────────────────────────────────


class TestGenerateSimulationSlurmConf:
    def test_contains_required_sections(self):
        conf = generate_simulation_slurm_conf(["c1", "c2"])
        required = [
            "ClusterName=linux",
            "SlurmctldHost=slurmctld",
            "AuthType=auth/munge",
            "SchedulerType=sched/backfill",
            "SelectType=select/cons_tres",
            "SlurmdParameters=config_overrides",
            "PriorityType=priority/multifactor",
            "PriorityWeightFairshare=10000",
            "AccountingStorageType=accounting_storage/slurmdbd",
            "AccountingStorageEnforce=associations,limits,qos",
        ]
        for item in required:
            assert item in conf, f"Missing: {item}"

    def test_node_definition(self):
        conf = generate_simulation_slurm_conf(["c1", "c2", "c3"])
        assert "NodeName=c[1-3]" in conf
        assert "CPUs=1000" in conf
        assert "RealMemory=500000" in conf

    def test_custom_cpus(self):
        conf = generate_simulation_slurm_conf(["c1"], cpus_per_node=500)
        assert "CPUs=500" in conf

    def test_partition(self):
        conf = generate_simulation_slurm_conf(["c1", "c2"])
        assert "PartitionName=normal" in conf
        assert "Default=YES" in conf

    def test_single_node(self):
        conf = generate_simulation_slurm_conf(["c1"])
        assert "NodeName=c1" in conf

    def test_has_timestamp(self):
        conf = generate_simulation_slurm_conf(["c1"])
        assert "Timestamp:" in conf

    def test_priority_weights(self):
        conf = generate_simulation_slurm_conf(["c1"])
        assert "PriorityWeightAge=1000" in conf
        assert "PriorityWeightFairshare=10000" in conf
        assert "PriorityWeightJobSize=500" in conf
        assert "PriorityWeightPartition=1000" in conf
        assert "PriorityWeightQOS=2000" in conf


# ── CLI command tests ───────────────────────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_cluster_running():
    with patch("slurm_playground.simulate.is_cluster_running", return_value=True):
        yield


@pytest.fixture
def mock_cluster_stopped():
    with patch("slurm_playground.simulate.is_cluster_running", return_value=False):
        yield


class TestSetupCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(simulate, ["setup"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestTeardownCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(simulate, ["teardown"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestStatusCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(simulate, ["status"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_no_simulation(self, runner, mock_cluster_running):
        mock_result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("slurm_playground.simulate.run_in_slurmctld", return_value=mock_result):
            result = runner.invoke(simulate, ["status"])
            assert result.exit_code == 0
            assert "No simulation detected" in result.output
