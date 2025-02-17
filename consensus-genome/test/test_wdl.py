import os
import json
import zipfile
import gzip
import tempfile
from subprocess import CalledProcessError

import yaml
from test_util import WDLTestCase


class TestConsensusGenomes(WDLTestCase):
    wdl = os.path.join(os.path.dirname(__file__), "..", "run.wdl")
    with open(os.path.join(os.path.dirname(__file__), "local_test.yml")) as fh:
        common_inputs = yaml.safe_load(fh)
    sc2_ref_fasta = "s3://idseq-public-references/consensus-genome/MN908947.3.fa"

    def test_sars_cov2_illumina_cg(self):
        fastqs_0 = os.path.join(os.path.dirname(__file__), "sample_sars-cov-2_paired_r1.fastq.gz")
        fastqs_1 = os.path.join(os.path.dirname(__file__), "sample_sars-cov-2_paired_r2.fastq.gz")
        args = ["sample=test_sample", f"fastqs_0={fastqs_0}", f"fastqs_1={fastqs_1}", "technology=Illumina",
                f"ref_fasta={self.sc2_ref_fasta}"]
        res = self.run_miniwdl(args)
        outputs = res["outputs"]
        with open(outputs["consensus_genome.compute_stats_out_output_stats"]) as fh:
            output_stats = json.load(fh)
        self.assertEqual(output_stats["sample_name"], "test_sample")
        # TODO: track non-determinism (888.xx vs 889.xx coverage)
        self.assertGreater(output_stats["depth_avg"], 888)
        self.assertEqual(output_stats["total_reads"], 187444)
        self.assertEqual(output_stats["mapped_reads"], 187211)
        self.assertEqual(output_stats["mapped_paired"], 187150)
        self.assertEqual(output_stats["ercc_mapped_reads"], 0)
        self.assertEqual(output_stats["ref_snps"], 7)
        self.assertEqual(output_stats["ref_mnps"], 0)
        for output_name, output in outputs.items():
            if output_name in {"consensus_genome.minion_log", "consensus_genome.vadr_errors"}:
                continue
            if not isinstance(output, list):
                output = [output]
            for filename in output:
                self.assertGreater(os.path.getsize(filename), 0)

    def test_vadr_error_caught(self):
        # use the long filename error as a proxy for testing VADR error handling
        fastqs_0 = os.path.join(os.path.dirname(__file__), "sample_sars-cov-2_paired_r1.fastq.gz")
        fastqs_1 = os.path.join(os.path.dirname(__file__), "sample_sars-cov-2_paired_r2.fastq.gz")
        vadr_opts_string = ("-s -r --nomisc --mkey NC_045512 --lowsim5term 2 --lowsim3term 2 --fstlowthr 0.0 "
                            "--alt_fail lowscore,fsthicnf,fstlocnf")
        args = ["sample=test_sample_really_really_really_long_sample_name_over_50_chars",
                f"fastqs_0={fastqs_0}", f"fastqs_1={fastqs_1}", "technology=Illumina",
                f"vadr_options={vadr_opts_string}", f"ref_fasta={self.sc2_ref_fasta}"]
        res = self.run_miniwdl(args=args)
        self.assertIn("consensus_genome.vadr_errors", res["outputs"])
        self.assertEqual(res["outputs"]["consensus_genome.vadr_alerts_out"], None)
        self.assertEqual(res["outputs"]["consensus_genome.vadr_quality_out"], None)

    def test_vadr_flag_works(self):
        fastqs_0 = os.path.join(os.path.dirname(__file__), "sample_sars-cov-2_paired_r1.fastq.gz")
        fastqs_1 = os.path.join(os.path.dirname(__file__), "sample_sars-cov-2_paired_r2.fastq.gz")
        args = ["sample=test_sample_really_really_really_long_sample_name_over_50_chars",
                f"fastqs_0={fastqs_0}", f"fastqs_1={fastqs_1}", "technology=Illumina",
                f"ref_fasta={self.sc2_ref_fasta}"]
        res = self.run_miniwdl(args=args)
        self.assertIn("consensus_genome.vadr_alerts_out", res["outputs"])
        self.assertIn("consensus_genome.vadr_alerts_out", res["outputs"])
        print(res["outputs"])
        print(res["outputs"]["consensus_genome.vadr_errors"])
        self.assertEqual(res["outputs"]["consensus_genome.vadr_errors"], None)

    # test the depths associated with SNAP ivar trim -x 5
    def test_sars_cov2_illumina_cg_snap(self):
        fastqs_0 = os.path.join(os.path.dirname(__file__), "snap_top10k_R1_001.fastq.gz")
        fastqs_1 = os.path.join(os.path.dirname(__file__), "snap_top10k_R1_001.fastq.gz")
        args = ["sample=test_snap", f"fastqs_0={fastqs_0}", f"fastqs_1={fastqs_1}", "technology=Illumina",
                "primer_bed=s3://idseq-public-references/consensus-genome/snap_primers.bed",
                f"ref_fasta={self.sc2_ref_fasta}"]
        res = self.run_miniwdl(args)
        outputs = res["outputs"]
        with open(outputs["consensus_genome.compute_stats_out_output_stats"]) as fh:
            output_stats = json.load(fh)
        self.assertEqual(output_stats["sample_name"], "test_snap")
        self.assertGreater(output_stats["depth_avg"], 7)
        self.assertLess(output_stats["depth_avg"], 8)
        self.assertGreater(output_stats["depth_q.5"], 3.9)
        self.assertLess(output_stats["depth_q.5"], 4.5)
        self.assertGreater(output_stats["depth_q.75"], 10.9)
        self.assertGreater(output_stats["depth_frac_above_10x"], 0.28)
        self.assertGreater(output_stats["depth_frac_above_25x"], 0.03)
        self.assertGreater(output_stats["depth_frac_above_25x"], 0.03)

    def test_sars_cov2_ont_cg_no_reads(self):
        fastqs_0 = os.path.join(os.path.dirname(__file__), "MT007544.fastq.gz")
        args = ["sample=test_sample", f"fastqs_0={fastqs_0}", "technology=ONT", f"ref_fasta={self.sc2_ref_fasta}"]
        with self.assertRaises(CalledProcessError) as ecm:
            self.run_miniwdl(args)
        self.assertRunFailed(ecm, task="RemoveHost", error="InsufficientReadsError", cause="No reads after RemoveHost")

    def test_sars_cov2_ont_cg(self):
        fastqs_0 = os.path.join(os.path.dirname(__file__), "Ct20K.fastq.gz")
        args = ["sample=test_sample", f"fastqs_0={fastqs_0}", "technology=ONT", f"ref_fasta={self.sc2_ref_fasta}"]
        res = self.run_miniwdl(args)
        outputs = res["outputs"]
        with open(outputs["consensus_genome.compute_stats_out_output_stats"]) as fh:
            output_stats = json.load(fh)
        self.assertEqual(output_stats["sample_name"], "test_sample")
        self.assertGreater(output_stats["depth_avg"], 13)
        self.assertGreater(output_stats["depth_frac_above_10x"], 0.5)
        self.assertEqual(output_stats["depth_frac_above_100x"], 0)
        self.assertEqual(output_stats["total_reads"], 1793)
        self.assertEqual(output_stats["mapped_reads"], 1347)
        self.assertEqual(output_stats["mapped_paired"], 0)
        self.assertNotIn("ercc_mapped_reads", output_stats)
        self.assertEqual(output_stats["ref_snps"], 10)
        self.assertEqual(output_stats["ref_mnps"], 0)
        self.assertEqual(output_stats["n_actg"], 7864)
        self.assertEqual(output_stats["n_missing"], 22039)
        self.assertEqual(output_stats["n_gap"], 0)
        self.assertEqual(output_stats["n_ambiguous"], 0)
        for output_name, output in outputs.items():
            if output_name in {"consensus_genome.quantify_erccs_out_ercc_out",
                               "consensus_genome.filter_reads_out_filtered_fastqs",
                               "consensus_genome.trim_reads_out_trimmed_fastqs",
                               "consensus_genome.vadr_errors"}:
                continue
            if not isinstance(output, list):
                output = [output]
            for filename in output:
                self.assertGreater(os.path.getsize(filename), 0)

    def test_sars_cov2_ont_cg_no_length_filter(self):
        """
        Ensures that the apply_length_filter=false option has an effect by truncating every other input read
        and asserting lower coverage in the output
        """
        fastqs_0 = os.path.join(os.path.dirname(__file__), "Ct20K.fastq.gz")
        tf = tempfile.NamedTemporaryFile(prefix=__name__, suffix=".fastq.gz")
        with gzip.open(fastqs_0, mode="r") as in_fh, gzip.open(tf.name, mode="w") as out_fh:
            lineno = 0
            while True:
                header, seq, sep, qual = in_fh.readline(), in_fh.readline(), in_fh.readline(), in_fh.readline()
                if not header:
                    break
                if lineno % 2 == 0:
                    seq, qual = seq[:100] + b"\n", qual[:100] + b"\n"
                out_fh.write(header + seq + sep + qual)
                lineno += 1
        args = ["sample=test_sample", f"fastqs_0={tf.name}", "technology=ONT", f"ref_fasta={self.sc2_ref_fasta}",
                "apply_length_filter=false"]
        res = self.run_miniwdl(args)
        outputs = res["outputs"]
        with open(outputs["consensus_genome.compute_stats_out_output_stats"]) as fh:
            output_stats = json.load(fh)
        self.assertEqual(output_stats["sample_name"], "test_sample")
        self.assertGreater(output_stats["depth_avg"], 6)
        self.assertLess(output_stats["depth_avg"], 7)

    def test_sars_cov2_ont_cg_input_file_format(self):
        """
        Tests that .fq.gz inputs are correctly converted to .fastq.gz formats to ensure they are read by guppyplex in
        ApplyLengthFilter
        """
        fastqs = os.path.join(os.path.dirname(__file__), "Ct20K.fq.gz")
        res = self.run_miniwdl(task="ValidateInput", args=["prefix=test", f"fastqs={fastqs}", "technology=ONT"])
        for output_name, output in res["outputs"].items():
            for filename in output:
                self.assertTrue(filename.endswith(".fastq.gz"))
                self.assertGreater(os.path.getsize(filename), 0)

    def test_general_cg(self):
        fastqs_0 = os.path.join(os.path.dirname(__file__), "SRR11741455_65054_nh_R1.fastq.gz")
        fastqs_1 = os.path.join(os.path.dirname(__file__), "SRR11741455_65054_nh_R2.fastq.gz")
        args = ["sample=test_sample", f"fastqs_0={fastqs_0}", f"fastqs_1={fastqs_1}", "technology=Illumina",
                "filter_reads=false", "ref_accession_id=MF965207.1"]

        res = self.run_miniwdl(args)
        for output_name, output in res["outputs"].items():
            if isinstance(output, str):
                self.assertGreater(os.path.getsize(output), 0)
            elif output:
                for path in output:
                    self.assertGreater(os.path.getsize(path), 0)
        with open(res["outputs"]["consensus_genome.compute_stats_out_output_stats"]) as fh:
            output_stats = json.load(fh)
        self.assertEqual(output_stats["sample_name"], "test_sample")
        self.assertGreater(output_stats["depth_avg"], 510)
        self.assertGreaterEqual(output_stats["depth_frac_above_10x"], 1.0)
        self.assertGreaterEqual(output_stats["depth_frac_above_100x"], 0.99)
        self.assertEqual(output_stats["total_reads"], 100000)
        self.assertEqual(output_stats["mapped_reads"], 55684)
        self.assertEqual(output_stats["mapped_paired"], 55676)
        self.assertEqual(output_stats["ercc_mapped_reads"], 0)
        self.assertEqual(output_stats["ref_snps"], 0)
        self.assertEqual(output_stats["ref_mnps"], 0)
        self.assertEqual(output_stats["n_actg"], 15312)
        self.assertEqual(output_stats["n_missing"], 0)
        self.assertEqual(output_stats["n_gap"], 0)
        self.assertEqual(output_stats["n_ambiguous"], 4)

        self.assertEqual(res["outputs"]["consensus_genome.vadr_alerts_out"], None)
        self.assertEqual(res["outputs"]["consensus_genome.vadr_quality_out"], None)
        self.assertEqual(res["outputs"]["consensus_genome.vadr_errors"], None)

        args.append(f"ref_fasta={self.sc2_ref_fasta}")
        with self.assertRaises(CalledProcessError) as ecm:
            self.run_miniwdl(args)
        self.assertRunFailed(ecm, task="MakeConsensus", error="InsufficientReadsError",
                             cause="No reads after MakeConsensus")

    def test_zip_outputs(self):
        res = self.run_miniwdl(task="ZipOutputs", args=["prefix=test", f"outputFiles={self.wdl}"])
        with zipfile.ZipFile(res["outputs"]["ZipOutputs.output_zip"]) as fh:
            self.assertEqual(fh.namelist(), ["run.wdl"])

    def test_fetch_sequence_by_accession_id(self):
        res = self.run_miniwdl(task="FetchSequenceByAccessionId", args=["accession_id=NC_000913.3"])
        with open(res["outputs"]["FetchSequenceByAccessionId.sequence_fa"]) as fh:
            self.assertEqual(fh.readline().strip(), ">NC_000913.3")
            self.assertTrue(fh.readline().startswith("AGCTTTTCATTCTGACTGCAACGGGCAATATGTCTCTG"))

        with self.assertRaises(CalledProcessError) as ecm:
            self.run_miniwdl(task="FetchSequenceByAccessionId", args=["accession_id=NO_ACCESSION_ID"])
        self.assertRunFailed(ecm, task="FetchSequenceByAccessionId",
                             error="AccessionIdNotFound", cause="Accession ID NO_ACCESSION_ID not found in the index")
