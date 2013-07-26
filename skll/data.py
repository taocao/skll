# Copyright (C) 2012-2013 Educational Testing Service

# This file is part of SciKit-Learn Lab.

# SciKit-Learn Lab is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# SciKit-Learn Lab is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with SciKit-Learn Lab.  If not, see <http://www.gnu.org/licenses/>.

'''
Handles loading data from various types of data files.

:author: Dan Blanchard (dblanchard@ets.org)
:author: Michael Heilman (mheilman@ets.org)
:author: Nitin Madnani (nmadnani@ets.org)
:organization: ETS
'''

from __future__ import print_function, unicode_literals

import json
import sys
from csv import DictReader, excel_tab
from itertools import islice
from multiprocessing import Pool
from operator import itemgetter

import numpy as np
from bs4 import UnicodeDammit
from collections import namedtuple
from six import iteritems
from six.moves import map, zip
from sklearn.feature_extraction import DictVectorizer


ExamplesTuple = namedtuple('ExamplesTuple', ['ids', 'classes', 'features',
                                             'feat_vectorizer'])


def _ids_for_gen_func(example_gen_func, path, has_labels):
    '''
    Little helper function to return an array of IDs for a given example
    generator (and whether or not the examples have labels).
    '''
    return np.array([curr_id for curr_id, _, _ in
                     example_gen_func(path, has_labels=has_labels, quiet=True)])


def _classes_for_gen_func(example_gen_func, path, has_labels):
    '''
    Little helper function to return an array of classes for a given example
    generator (and whether or not the examples have labels).
    '''
    return np.array([class_name for _, class_name, _ in
                     example_gen_func(path, has_labels=has_labels, quiet=True)])


def _features_for_gen_func(example_gen_func, path, has_labels, sparse, quiet):
    '''
    Little helper function to return a sparse matrix of features and feature
    vectorizer for a given example generator (and whether or not the examples
    have labels).
    '''
    feat_vectorizer = DictVectorizer(sparse=sparse)
    feat_dict_generator = map(itemgetter(2),
                              example_gen_func(path, has_labels=has_labels,
                                               quiet=quiet))
    features = feat_vectorizer.fit_transform(feat_dict_generator)
    return features, feat_vectorizer


def load_examples(path, has_labels=True, sparse=True, quiet=False):
    '''
    Loads examples in the TSV, JSONLINES (a json dict per line), or MegaM
    formats.

    If you would like to include example/instance IDs in your files, they must
    be specified in the following ways:

    * MegaM: As a comment line directly preceding the line with feature values.
    * TSV: An "id" column.
    * JSONLINES: An "id" key in each JSON dictionary.

    :param path: The path to the file to load the examples from.
    :type path: basestring
    :param has_labels: Whether or not the file contains class labels.
    :type has_labels: bool
    :param sparse: Whether or not to store the features in a numpy CSR matrix.
    :type sparse: bool
    :param quiet: Do not print "Loading..." status message to stderr.
    :type quiet: bool

    :return: 4-tuple of an array example ids, an array of class labels, a
             scipy CSR matrix of features, and a DictVectorizer containing
             the mapping between feature names and the column indices in
             the feature matrix.
    '''
    # Build an appropriate generator for examples so we process the input file
    # through the feature vectorizer without using tons of memory
    if path.endswith(".tsv"):
        example_gen_func = _tsv_dict_iter
    elif path.endswith(".jsonlines"):
        example_gen_func = _json_dict_iter
    elif path.endswith(".megam"):
        example_gen_func = _megam_dict_iter
    else:
        raise Exception('Example files must be in either TSV, MegaM, or ' +
                        '.jsonlines format. ' +
                        'You specified: {}'.format(path))

    # Create generators that we can use to create numpy arrays without wasting
    # memory (even though this requires reading the file multiple times).
    # Do this using a process pool so that we can clear out the temporary
    # variables more easily and do these in parallel.
    pool = Pool(3)

    ids_result = pool.apply_async(_ids_for_gen_func, args=(example_gen_func,
                                                           path,
                                                           has_labels))
    classes_result = pool.apply_async(_classes_for_gen_func,
                                      args=(example_gen_func, path, has_labels))
    features_result = pool.apply_async(_features_for_gen_func,
                                       args=(example_gen_func, path, has_labels,
                                             sparse, quiet))

    # Wait for processes to complete and store results
    pool.close()
    pool.join()
    ids = ids_result.get()
    classes = classes_result.get()
    features, feat_vectorizer = features_result.get()

    return ExamplesTuple(ids, classes, features, feat_vectorizer)


def _sanitize_line(line):
    '''
    :param line: The line to clean up.
    :type line: string

    :returns: Copy of line with all non-ASCII characters replaced with
    <U1234> sequences where 1234 is the value of ord() for the character.
    '''
    char_list = []
    for char in line:
        char_num = ord(char)
        char_list.append('<U{}>'.format(char_num) if char_num > 127 else char)
    return ''.join(char_list)


def _safe_float(text):
    '''
    Attempts to convert a string to a float, but if that's not possible, just
    returns the original value.
    '''
    try:
        return float(text)
    except ValueError:
        return text


def _json_dict_iter(path, has_labels=True, quiet=False):
    '''
    Convert current line in .jsonlines file to a dictionary with the
    following fields: "SKLL_ID" (originally "id"), "SKLL_CLASS_LABEL"
    (originally "y"), and all of the feature-values in the sub-dictionary
    "x". Basically, we're flattening the structure, but renaming "y" and "id"
    to prevent possible conflicts with feature names in "x".

    :param path: Path to .jsonlines file
    :type path: string
    :param has_labels: Whether or not the JSON dicts will contain a class label,
                       "y".
    :type has_labels: bool
    :param quiet: Do not print "Loading..." status message to stderr.
    :type quiet: bool
    '''
    with open(path) as f:
        if not quiet:
            print("Loading {}...".format(path), end="", file=sys.stderr)
            sys.stderr.flush()
        for example_num, line in enumerate(f):
            example = json.loads(line.strip())
            curr_id = example.get("id", "EXAMPLE_{}".format(example_num))
            class_name = example["y"] if has_labels else None
            example = example["x"]

            yield curr_id, class_name, example

            if not quiet and example_num % 100 == 0:
                print(".", end="", file=sys.stderr)
        if not quiet:
            print("done", file=sys.stderr)


def _megam_dict_iter(path, has_labels=True, quiet=False):
    '''
    Generator that yields tuples of IDs, classes, and dictionaries mapping from
    features to values for each pair of lines in the MegaM -fvals file specified
    by path.

    :param path: Path to MegaM file (-fvals format)
    :type path: basestring
    :param has_labels: Whether or not the file has a class label separated by
                       a tab before the space delimited feature-value pairs.
    :type has_labels: bool
    :param quiet: Do not print "Loading..." status message to stderr.
    :type quiet: bool
    '''

    if not quiet:
        print("Loading {}...".format(path), end="", file=sys.stderr)
        sys.stderr.flush()
    with open(path, 'rb') as megam_file:
        example_num = 0
        curr_id = 'EXAMPLE_0'
        for line in megam_file:
            # Process encoding
            line = UnicodeDammit(line, ['utf-8', 'windows-1252']).unicode_markup
            line = _sanitize_line(line.strip())
            # Handle instance lines
            if line.startswith('#'):
                curr_id = line[1:].strip()
            elif line and line not in ['TRAIN', 'TEST', 'DEV']:
                split_line = line.split()
                curr_info_dict = {}

                if has_labels:
                    class_name = split_line[0]
                    field_pairs = split_line[1:]
                else:
                    class_name = None
                    field_pairs = split_line

                if len(field_pairs) > 0:
                    # Get current instances feature-value pairs
                    field_names = islice(field_pairs, 0, None, 2)
                    # Convert values to floats, because otherwise features'll
                    # be categorical
                    field_values = (_safe_float(val) for val in
                                    islice(field_pairs, 1, None, 2))

                    # TODO: Add some sort of check for duplicate feature names

                    # Add the feature-value pairs to dictionary
                    curr_info_dict.update(zip(field_names, field_values))

                yield curr_id, class_name, curr_info_dict

                # Set default example ID for next instance, in case we see a
                # line without an ID.
                example_num += 1
                curr_id = 'EXAMPLE_{}'.format(example_num)

                if not quiet and example_num % 100 == 0:
                    print(".", end="", file=sys.stderr)
        if not quiet:
            print("done", file=sys.stderr)


def _tsv_dict_iter(path, has_labels=True, quiet=False):
    '''
    Generator that yields tuples of IDs, classes, and dictionaries mapping from
    features to values for each pair of lines in the MegaM -fvals file specified
    by path.

    :param path: Path to TSV
    :type path: string
    :param has_labels: Whether or not the TSV's first column is a class label.
    :type has_labels: bool
    :param quiet: Do not print "Loading..." status message to stderr.
    :type quiet: bool
    '''
    if not quiet:
        print("Loading {}...".format(path), end="", file=sys.stderr)
        sys.stderr.flush()
    with open(path) as f:
        reader = DictReader(f, dialect=excel_tab)
        for example_num, row in enumerate(reader):
            if has_labels:
                class_name = row[reader.fieldnames[0]]
                del row[reader.fieldnames[0]]
            else:
                class_name = None

            if "id" not in row:
                curr_id = "EXAMPLE_{}".format(example_num)
            else:
                curr_id = row["id"]
                del row["id"]

            # Convert features to flaot
            for fname, fval in iteritems(row):
                fval_float = _safe_float(fval)
                # we don't need to explicitly store zeros
                if fval_float != 0.0:
                    row[fname] = fval_float

            yield curr_id, class_name, row

            if not quiet and example_num % 100 == 0:
                print(".", end="", file=sys.stderr)
        if not quiet:
            print("done", file=sys.stderr)

