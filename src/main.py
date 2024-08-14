from PIL import Image, ImageOps
import argparse
import itertools
import json
import logging
import os
import pathlib

APP_NAME         = 'magnet-framer'
SCRIPT_DIR_PATH  = pathlib.Path(__file__).parent.resolve()
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR_PATH, 'config.json')
LOG_PATH         = os.path.join(SCRIPT_DIR_PATH, f'{APP_NAME}.log')

json_config    = None
config         = None
current_config = None

class Crop:
    def __init__(self, left, top, right, bottom):
        self.left   = left
        self.top    = top
        self.right  = right
        self.bottom = bottom

class CustomFormatter(logging.Formatter):

    grey         = '\x1b[38;20m'
    yellow       = '\x1b[33;20m'
    red          = '\x1b[31;20m'
    bold_red     = '\x1b[31;1m'
    light_purple = '\x1b[38;5;105m'
    reset        = '\x1b[0m'
    format = '%(asctime)s.%(msecs)03d %(name)-20s %(levelname)-8s %(message)s'

    FORMATS = {
        logging.DEBUG:    grey         + format + reset,
        logging.INFO:     light_purple + format + reset,
        logging.WARNING:  yellow       + format + reset,
        logging.ERROR:    red          + format + reset,
        logging.CRITICAL: bold_red     + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
        return formatter.format(record)

def crop_image(image):
    crop = current_config['crop']
    coordinates = crop.left, crop.top, image.width - crop.right, image.height - crop.bottom
    cropped_image = image.crop(coordinates)

    return cropped_image

def scale_image(image, frame):
    scale_factor = current_config['scale-factor']
    scale_factor = scale_factor * min(frame.width / image.width, frame.height / image.height)
    new_width  = int(image.width * scale_factor)
    new_height = int(image.height * scale_factor)
    scaled_image = image.resize((new_width, new_height))

    return scaled_image

def pad_image(image, frame):
    horizontal_correction = 0
    vertical_correction   = 0

    left_padding   = ((frame.width - image.width) // 2) + horizontal_correction
    top_padding    = ((frame.height - image.height) // 2) + vertical_correction
    right_padding  = frame.width - image.width - left_padding
    bottom_padding = frame.height - image.height - top_padding

    padding = (left_padding, top_padding, right_padding, bottom_padding)

    padded_image = ImageOps.expand(image, padding, fill='red' if config.debug else 'white')

    return padded_image

def frame_image(image, frame):
    x = (frame.width - image.width) // 2
    y = (frame.height - image.height) // 2

    framed_image = image.copy()
    framed_image.paste(frame, (x, y), frame)
    framed_image = framed_image.convert('RGB')

    return framed_image

def rotate_image(image):
    rotated_image = image.rotate(90, expand=True)

    return rotated_image

def image_orientation(image):
    if (image.width > image.height):
        return 'landscape'
    elif (image.width < image.height):
        return 'portrait'
    else:
        return 'square'

def output_filename_with_postfix(filename, postfix):
    splitted_filename = os.path.splitext(filename)
    newFilename = os.path.join(config.output, splitted_filename[0] + postfix + splitted_filename[1])
    logging.debug(f'generated output filename: {newFilename}')
    return newFilename

def save_image(image, filename, postfix):
    final_name = output_filename_with_postfix(filename, postfix)
    image.convert('RGB').save(final_name)

def set_current_config(image):
    global current_config
    if image_orientation(image) == 'landscape':
        current_config = {
            'frame-path': json_config['land-frame-path'],
            'crop': Crop(json_config['land-crop-left'], json_config['land-crop-top'], json_config['land-crop-right'], json_config['land-crop-bottom']),
            'scale-factor': json_config['land-scale-factor'],
        }
    elif image_orientation(image) == 'portrait':
        current_config = {
            'frame-path': json_config['port-frame-path'],
            'crop': Crop(json_config['port-crop-left'], json_config['port-crop-top'], json_config['port-crop-right'], json_config['port-crop-bottom']),
            'scale-factor': json_config['port-scale-factor'],
        }
    else:
        logging.error("Can't process square image")
        exit(1)

def unset_current_config():
    global current_config
    current_config = None

def process():
    for filename in os.listdir(config.input):
        if filename.endswith('.jpg'):
            counter = itertools.count(start=0)

            img_path = os.path.join(config.input, filename)
            logging.info(f'file {img_path} status: processing...')

            original_image = Image.open(img_path).convert('RGBA')
            logging.debug(f'Image loaded successfully')
            logging.debug(f'Image size: {original_image.size}')
            logging.debug(f'Image orientation: {image_orientation(original_image)}')
            set_current_config(original_image)
            if config.debug:
                save_image(original_image, filename, f'_{next(counter)}_original')

            frame = Image.open(current_config['frame-path']).convert('RGBA')
            logging.debug(f'Frame loaded successfully')
            logging.debug(f'Frame size: {frame.size}')
            logging.debug(f'Frame orientation: {image_orientation(frame)}')

            cropped_image = crop_image(original_image)
            logging.debug(f'Image cropped to size {cropped_image.size}')
            if config.debug:
                save_image(cropped_image, filename, f'_{next(counter)}_cropped')

            scaled_image = scale_image(cropped_image, frame)
            logging.debug(f'Image scaled to size {scaled_image.size}')
            if config.debug:
                save_image(scaled_image, filename, f'_{next(counter)}_scaled')

            padded_image = pad_image(scaled_image, frame)
            logging.debug(f'Image padded to size {padded_image.size}')
            if config.debug:
                save_image(padded_image, filename, f'_{next(counter)}_padded')

            framed_image = frame_image(padded_image, frame)
            logging.debug(f'Image framed successfully')

            if (json_config['rotate-to-landscape'] and image_orientation(original_image) == 'portrait'):
                final_image = rotate_image(framed_image)
            else:
                final_image = framed_image

            save_image(final_image, filename, f'_{next(counter)}_framed' if config.debug else '_framed')
            unset_current_config()
            logging.info(f'file {img_path} status: done')

def configure_logging(logLevel):
    logging.basicConfig(level=logLevel,
                        format='%(asctime)s.%(msecs)03d %(name)-20s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M',
                        filename=LOG_PATH,
                        filemode='w')
    console = logging.StreamHandler()
    formatter = CustomFormatter()
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)

def configure():
    global json_config
    global config

    with open(CONFIG_FILE_PATH, 'r') as f:
        json_config = json.load(f)

    parser = argparse.ArgumentParser(description='Prepare images for printing on magnets')

    parser.add_argument('-i', '--input'          , type=str           , help='Path to input files directory' , default=json_config['input-path'])
    parser.add_argument('-o', '--output'         , type=str           , help='Path to output files directory', default=json_config['output-path'])
    parser.add_argument('-l', '--landscape-frame', type=str           , help='Path to landscape frame file'  , default=json_config['land-frame-path'])
    parser.add_argument('-p', '--portrait-frame' , type=str           , help='Path to portrait frame file'   , default=json_config['port-frame-path'])
    parser.add_argument('-d', '--debug'          , action='store_true', help='Run in debug mode'             , default=json_config['debug'])

    config = parser.parse_args()

    logLevel = logging.INFO
    if (config.debug):
        logLevel = logging.DEBUG
    configure_logging(logLevel)

def verify_input():
    if(not os.path.isdir(config.input)):
        logging.error(f'Input directory {config.input} does not exist')
        exit(1)
    if(not os.path.isdir(config.output)):
        logging.error(f'Output directory {config.output} does not exist')
        exit(1)

if __name__ == '__main__':
    configure()
    logging.info(f'--- {APP_NAME} start ---')
    verify_input()
    process()
    logging.info(f'---  {APP_NAME} End  ---')
