class DeviceBase:
    """
    Base class of an HDC-device
    """

    def __init__(self):
        self.features: dict[int, FeatureBase] = dict()


class FeatureBase:
    """
    Base class of a feature of an HDC-device
    """
    FeatureID: int

    def __init__(self, id: int):
        self.FeatureID = id
