# debugging plugin layouts
from paperpi.library.font_search 
font_path = locate_path('fonts')



# +
debugging_basic = {
    'title': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 2,
        'width': 1,
        'height': 1/3,
        'abs_coordinates': (0, 0),
        'rand': False,
        'font': font_path / 'Kanit/Kanit-Medium.ttf',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },
    'crash_rate': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 2,
        'width': 1/2,
        'height': 1/3,
        'abs_coordinates': (0, None),
        'relative': ['crash_rate', 'title'],
        'rand': False,
        'font': font_path / 'Kanit/Kanit-Medium.ttf',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },
    'priority': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 2,
        'width': 1/2,
        'height': 1/3,
        'abs_coordinates': (None, None),
        'relative': ['crash_rate', 'title'],
        'rand': False,
        'font': font_path / 'Kanit/Kanit-Medium.ttf',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },    
    'digit_time': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 2,
        'width': 1,
        'height': 1/3,
        'abs_coordinates': (0, None),
        'relative': ['digit_time', 'crash_rate'],
        'rand': False,
        'font': font_path / 'Kanit/Kanit-Medium.ttf',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },
    
}
# -

layout = debugging_basic
