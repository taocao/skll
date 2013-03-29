#!/usr/bin/env python
'''
Loads a trained model and outputs predictions based on input feature files.

@author: Dan Blanchard
@contact: dblanchard@ets.org
@organization: ETS
@date: February 2013
'''

from __future__ import print_function, unicode_literals

import argparse
from classifier import Classifier, load_examples, _REGRESSION_MODELS


class Predictor(object):
    """
    Little wrapper around a L{Classifier} to load models and get
    predictions for feature strings.
    """

    def __init__(self, model_prefix, threshold=None, positive_class=1):
        '''
        Initialize the predictor.

        @param model_prefix: Prefix to use when loading trained model (and its
                             vocab).
        @type model_prefix: C{basestring}
        @param threshold: If the model we're using is generating probabilities
                          of the positive class, return 1 if it meets/exceeds
                          the given threshold and 0 otherwise.
        @type threshold: C{float}
        @param positive_class: If the model is only being used to predict the
                               probability of a particular class, this
                               specifies the index of the class we're
                               predicting. 1 = second class, which is default
                               for binary classification.
        @type positive_class: C{int}
        '''
        self._classifier = Classifier()
        self._classifier.load_model('{}.model'.format(model_prefix))
        self._pos_index = positive_class
        self.threshold = threshold

    def predict(self, data):
        '''
        Return a list of predictions for a given numpy array of examples
        (which are dicts)
        '''
        # Must make a list around a dictionary to fit format that
        # Classifier.predict expects
        preds = self._classifier.predict(data).tolist()

        if self._classifier.probability:
            if self.threshold is None:
                return [pred[self._pos_index] for pred in preds]
            else:
                return [int(pred[self._pos_index] >= self.threshold)
                        for pred in preds]
        elif self._classifier.model_type in _REGRESSION_MODELS:
            return preds
        else:
            return [self._classifier.label_list[int(pred[0])] for pred in preds]


def main():
    ''' Main function that does all the work. '''
    # Get command line arguments
    parser = argparse.ArgumentParser(
        description="Loads a trained model and outputs predictions based \
                     on input feature files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        conflict_handler='resolve')
    parser.add_argument('model_prefix', help='Prefix to use when loading \
                                              trained model (and its vocab).')
    parser.add_argument('input_file',
                        help='A csv file, json file, or megam file \
                              (with or without the label column), \
                              with the appropriate suffix.',
                        nargs='+')
    parser.add_argument('-l', '--has_labels',
                        help="Indicates that the input file includes \
                              labels and that the features start at the \
                              2nd column for csv and megam files.",
                        action='store_true')
    parser.add_argument('-p', '--positive_class',
                        help="If the model is only being used to predict the \
                              probability of a particular class, this \
                              specifies the index of the class we're \
                              predicting. 1 = second class, which is default \
                              for binary classification. Keep in mind that \
                              classes are sorted lexicographically.",
                        default=1, type=int)
    parser.add_argument('-t', '--threshold',
                        help="If the model we're using is generating \
                              probabilities of the positive class, return 1 \
                              if it meets/exceeds the given threshold and 0 \
                              otherwise.",
                        type=float)
    args = parser.parse_args()

    # Create the classifier and load the model
    predictor = Predictor(args.model_prefix,
                          positive_class=args.positive_class,
                          threshold=args.threshold)

    for input_file in args.input_file:
        data = load_examples(input_file, has_labels=args.has_labels)
        for pred in predictor.predict(data):
            print(pred)


if __name__ == '__main__':
    main()