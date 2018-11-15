import argparse
import misoctl.upload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='koji',
                        help='koji client profile (defaults to "koji")')

    # top-level subcommands:
    subparsers = parser.add_subparsers(dest='subcommand')
    subparsers.required = True

    # add arguments for each subcommand:
    misoctl.upload.add_parser(subparsers)

    args = parser.parse_args()

    args.func(args)
