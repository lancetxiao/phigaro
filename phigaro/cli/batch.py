from __future__ import absolute_import

import argparse
import logging
import multiprocessing
import os
import sys
import uuid
from os.path import join, exists

import yaml

from phigaro.context import Context
from phigaro.scheduling.path import sample_name
from phigaro.scheduling.runner import run_tasks_chain
from phigaro.scheduling.task.gene_mark import GeneMarkTask
from phigaro.scheduling.task.hmmer import HmmerTask
from phigaro.scheduling.task.dummy import DummyTask
from phigaro.scheduling.task.parse_hmmer import ParseHmmerTask
from phigaro.scheduling.task.run_phigaro import RunPhigaroTask


def parse_substitute_output(subs):
    res = {}
    for sub in subs:
        task_name, output = sub.split(":")
        res[task_name] = DummyTask(output)
    return res


def create_task(substitutions, task_class, *args, **kwargs):
    task = task_class(*args, **kwargs)
    if task.task_name in substitutions:
        print('Substituting output for {}: {}'.format(
            task.task_name, substitutions[task.task_name].output()
        ))

        return substitutions[task.task_name]


def main():
    default_config_path = join(os.getenv('HOME'), '.phigaro', 'config.yml')
    parser = argparse.ArgumentParser(
        description='Phigaro is a scalable command-line tool for predictions phages and prophages '
                    'from nucleid acid sequences (including metagenomes) and '
                    'is based on phage genes HMMs and a smoothing window algorithm.',
    )
    parser.add_argument('-f', '--fasta-file', help='Assembly scaffolds\contigs or full genomes', required=True)
    parser.add_argument('-c', '--config', default=default_config_path, help='config file')
    parser.add_argument('-v', '--verbose', action='store_true', help='print debug information (for developers)')
    parser.add_argument('-t', '--threads',
                        type=int,
                        default=multiprocessing.cpu_count(),
                        help='num of threads ('
                             'default is num of CPUs={})'.format(multiprocessing.cpu_count()))

    parser.add_argument('-S', '--substitute-output', action='append', )
    # help=argparse.SUPPRESS)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARN)
    logging.getLogger('sh.command').setLevel(logging.WARN)

    logger = logging.getLogger(__name__)

    substitutions = parse_substitute_output(args.substitute_output)

    if not exists(args.config):
        # TODO: pretty message
        print('Please create config file using phigaro-setup script')
        exit(1)

    with open(args.config) as f:
        logger.info('Using config file: {}'.format(args.config))
        config = yaml.load(f)

    filename = args.fasta_file
    sample = '{}-{}'.format(
        sample_name(filename),
        uuid.uuid4().hex
    )

    Context.initialize(
        sample=sample,
        config=config,
        threads=args.threads,
    )

    gene_mark_task = create_task(substitutions, GeneMarkTask, filename)
    hmmer_task = create_task(substitutions, HmmerTask, gene_mark_task=gene_mark_task)
    parse_hmmer_task = create_task(substitutions, ParseHmmerTask,
                                   gene_mark_task=gene_mark_task,
                                   hmmer_task=hmmer_task,
                                   )
    run_phigaro_task = create_task(substitutions, RunPhigaroTask, gene_mark_task=gene_mark_task, parse_hmmer_task=parse_hmmer_task)

    output_file = run_tasks_chain([
        gene_mark_task,
        hmmer_task,
        parse_hmmer_task,
        run_phigaro_task
    ])

    with open(output_file) as f:
        for line in f:
            sys.stdout.write(line)


if __name__ == '__main__':
    main()
