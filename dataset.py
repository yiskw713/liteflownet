import glob
import h5py
import io
import torch
import numpy as np
import torchvision
import os
import sys
from torch.utils.data import Dataset
from PIL import Image


def pil_loader(path):
    return Image.open(path)


def accimage_loader(path):
    try:
        import accimage
        return accimage.Image(path)
    except ModuleNotFoundError:
        # Potentially a decoding problem, fall back to PIL.Image
        torchvision.set_image_backend('PIL')
        return pil_loader(path)


def get_default_image_loader():
    torchvision.set_image_backend('accimage')

    return accimage_loader


def train_video_loader(
        loader, video_path, input_frames=64, transform=None, temp_downsamp_rate=2, image_file_format='hdf5'):
    """
    Return sequential 64 frames in video clips.
    A initial frame is randomly decided.
    Args:
        video_path: path for the video.
        input_frames: the number of frames you want to input to the model. (default 16)
        temp_downsamp_rate: temporal downsampling rate (default 2)
        image_file_format: 'jpg' or 'hdf5'
    """

    if image_file_format == 'jpg':
        # count the number of frames
        n_frames = len(glob.glob(os.path.join(video_path, '*.jpg')))
        start_frame = np.random.randint(
            1, max(1, n_frames - input_frames * temp_downsamp_rate))

        # loop padding if the number of frames of a video is smaller than input frames
        indices = [i for i in range(n_frames)]
        indices = indices[start_frame::temp_downsamp_rate]
        for i in indices:
            if len(indices) >= input_frames:
                break
            else:
                indices.append(i)

        clip = []
        for i in indices:
            # frame name: image_000001.jpg ~
            img_path = os.path.join(video_path, 'image_{:05d}.jpg'.format(i+1))
            img = loader(img_path)
            if transform is not None:
                img = transform(img)
            clip.append(img)

    elif image_file_format == 'hdf5':
        if video_path[-5:] != '.hdf5':
            video_path += '.hdf5'
        with h5py.File(video_path, 'r') as f:
            video = f['video']
            n_frames = len(video)
            clip = []

            start_frame = np.random.randint(
                0, max(1, n_frames - input_frames * temp_downsamp_rate))

            # loop padding if the number of frames of a video is smaller than input frames
            indices = [i for i in range(n_frames)]
            indices = indices[start_frame::temp_downsamp_rate]
            for i in indices:
                if len(indices) == input_frames:
                    break
                elif len(indices) > input_frames:
                    indices = indices[:input_frames]
                    break
                indices.append(i)

            for i in indices:
                img = Image.open(io.BytesIO(video[i]))
                if transform is not None:
                    img = transform(img)
                clip.append(img)
    else:
        print('You have to choose "jpg" or "hdf5" as image file format.')
        sys.exit(1)
    return clip


def feature_extract_loader(
        loader, video_path, transform=None, temp_downsamp_rate=2, image_file_format='hdf5'):
    """
    Return full temporal sequential frames in video clips.
    Args:
        video_path: path for the video.
        temp_downsamp_rate: temporal downsampling rate (default 2)
        image_file_format: 'jpg' or 'hdf5'
    """

    if image_file_format == 'jpg':
        # count the number of frames
        n_frames = len(glob.glob(os.path.join(
            video_path, '*.{}'.format(image_file_format))))

        clip = []
        for i in range(0, n_frames, temp_downsamp_rate):
            img_path = os.path.join(video_path, 'image_{:05d}.jpg'.format(i))
            img = loader(img_path)
            if transform is not None:
                img = transform(img)
            clip.append(img)

    elif image_file_format == 'hdf5':
        if video_path[-5:] != '.hdf5':
            video_path += '.hdf5'
        with h5py.File(video_path, 'r') as f:
            video = f['video']
            n_frames = len(video)
            clip = []
            for i in range(0, n_frames, temp_downsamp_rate):
                img = Image.open(io.BytesIO(video[i]))

                if transform is not None:
                    img = transform(img)
                clip.append(img)
    else:
        print('You have to choose "jpg" or "hdf5" as image file format.')
        sys.exit(1)
    return clip


class MSR_VTT(Dataset):
    """
    Dataset class for MSR-VTT
    """

    def __init__(self, dataset_dir, temp_downsamp_rate=2, image_file_format='hdf5', transform=None):
        super().__init__()

        self.dataset_dir = dataset_dir
        self.image_file_format = image_file_format
        self.temp_downsamp_rate = temp_downsamp_rate

        if self.image_file_format == 'hdf5':
            self.video = glob.glob(os.path.join(self.dataset_dir, '*.hdf5'))
        elif self.image_file_format == 'jpg':
            self.video = glob.glob(os.path.join(self.dataset_dir, '*'))
        else:
            print('You have to choose "jpg" or "hdf5" as image file format.')
            sys.exit(1)

        self.transform = transform
        self.loader = get_default_image_loader()

    def __len__(self):
        return len(self.video)

    def __getitem__(self, idx):
        video_path = self.video[idx]

        clip = feature_extract_loader(
            self.loader, video_path, self.transform,
            self.temp_downsamp_rate, self.image_file_format
        )

        # clip.shape => (C, T, H, W)
        clip = torch.stack(clip, 0).permute(1, 0, 2, 3)

        video_id = os.path.relpath(video_path, self.dataset_dir)

        if self.image_file_format == 'hdf5':
            video_id = video_id[:-5]
        else:
            video_id = video_id[:-4]

        sample = {
            'clip': clip,
            'video_id': video_id,
        }

        return sample
