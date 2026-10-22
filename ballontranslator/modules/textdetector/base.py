import base64
import requests
import numpy as np
import cv2
from typing import List, Tuple

from ballontranslator.utils.textblock import TextBlock
from ballontranslator.utils.proj_imgtrans import ProjImgTrans

from ballontranslator.utils.registry import Registry
TEXTDETECTORS = Registry('textdetectors')
register_textdetectors = TEXTDETECTORS.register_module

from ..base import BaseModule, DEFAULT_DEVICE, DEVICE_SELECTOR
from ..exceptions import ModuleRunError

class TextDetectorBase(BaseModule):

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.name = ''
        for key in TEXTDETECTORS.module_dict:
            if TEXTDETECTORS.module_dict[key] == self.__class__:
                self.name = key
                break

    def _detect(self, img: np.ndarray, proj: ProjImgTrans) -> Tuple[np.ndarray, List[TextBlock]]:
        '''
        The proj context can be accessed via ```proj```
        '''
        raise NotImplementedError

    def setup_detector(self):
        raise NotImplementedError

    def detect(self, img: np.ndarray, proj: ProjImgTrans = None) -> Tuple[np.ndarray, List[TextBlock]]:
        if not self.all_model_loaded():
            self.load_model()

        try:
            # TODO: allow processing proj entirely in _detect and yield progress
            # All text detectors only support 3 channels input
            if img.ndim == 3 and img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

            mask, blk_list = self._detect(img, proj)
            calibrate = (
                self.params is not None and 'calibrate_source_font_size' in self.params
                and self.get_param_value('calibrate_source_font_size')
            )
            if calibrate:
                from ballontranslator.utils.font_size_estimation import estimate_source_ink_size
            character_extent = (
                calibrate and 'calibrate_character_extent' in self.params
                and bool(self.get_param_value('calibrate_character_extent'))
            )
            square_metric = (
                character_extent and ('square_character_area' not in self.params
                                      or bool(self.get_param_value('square_character_area')))
            )
            font_size_multiplier = (
                float(self.get_param_value('font size multiplier'))
                if calibrate and 'font size multiplier' in self.params else 1.0
            )
            for blk in blk_list:
                blk.det_model = self.name
                if calibrate:
                    size = estimate_source_ink_size(
                        img, blk, character_extent=character_extent, area_metric=character_extent,
                        square_metric=square_metric,
                    )
                    if size is not None:
                        size *= font_size_multiplier
                        blk._source_font_size_uses_character_extent = character_extent
                        blk._source_font_size_uses_ink_area = character_extent
                        blk._source_font_size_uses_squared_area = square_metric
                        blk._detected_font_size = size
                        blk.font_size = size
            return mask, blk_list
        except ModuleRunError:
            raise
        except Exception as e:
            raise ModuleRunError('textdetector', self.name, str(e)) from e
