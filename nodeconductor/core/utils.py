from collections import OrderedDict
from datetime import datetime
from operator import itemgetter
import time

from django.utils import timezone


def sort_dict(unsorted_dict):
    """
    Return a OrderedDict ordered by key names from the :unsorted_dict:
    """
    sorted_dict = OrderedDict()
    # sort items before inserting them into a dict
    for key, value in sorted(unsorted_dict.items(), key=itemgetter(0)):
        sorted_dict[key] = value
    return sorted_dict


def format_time_and_value_to_segment_list(time_and_value_list, segments_count, start_timestamp,
                                          end_timestamp, average=False):
    """
    Format time_and_value_list to time segments

    Parameters
    ----------
    time_and_value_list: list of tuples
        Have to be sorted by time
        Example: [(time, value), (time, value) ...]
    segments_count: integer
        How many segments will be in result
    Returns
    -------
    List of dictionaries
        Example:
        [{'from': time1, 'to': time2, 'value': sum_of_values_from_time1_to_time2}, ...]
    """
    segment_list = []
    time_step = (end_timestamp - start_timestamp) / segments_count
    for i in range(segments_count):
        segment_start_timestamp = start_timestamp + time_step * i
        segment_end_timestamp = segment_start_timestamp + time_step
        value_list = [
            value for time, value in time_and_value_list
            if time >= segment_start_timestamp and time < segment_end_timestamp]
        segment_value = sum(value_list)
        if average and len(value_list) != 0:
            segment_value /= len(value_list)

        segment_list.append({
            'from': segment_start_timestamp,
            'to': segment_end_timestamp,
            'value': segment_value,
        })
    return segment_list


def datetime_to_timestamp(datetime):
    return int(time.mktime(datetime.timetuple()))


def timestamp_to_datetime(timestamp):
    return datetime.fromtimestamp(int(timestamp)).replace(tzinfo=timezone.get_current_timezone())
