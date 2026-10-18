"""Small U-Net with a ResNet-18 encoder (shared by training and the API).
Two output channels: 0 = fruit, 1 = visible decay."""
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision


def _block(cin, cout):
    return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                         nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))


class UNetResNet18(nn.Module):
    def __init__(self, pretrained: bool = False, n_out: int = 2):
        super().__init__()
        r = torchvision.models.resnet18(weights="IMAGENET1K_V1" if pretrained else None)
        self.stem = nn.Sequential(r.conv1, r.bn1, r.relu)          # /2, 64
        self.pool = r.maxpool                                      # /4
        self.e1, self.e2, self.e3, self.e4 = r.layer1, r.layer2, r.layer3, r.layer4  # 64,128,256,512
        self.d4 = _block(512 + 256, 256)
        self.d3 = _block(256 + 128, 128)
        self.d2 = _block(128 + 64, 64)
        self.d1 = _block(64 + 64, 32)
        self.head = nn.Conv2d(32, n_out, 1)

    def forward(self, x):
        s = self.stem(x); e1 = self.e1(self.pool(s)); e2 = self.e2(e1); e3 = self.e3(e2); e4 = self.e4(e3)
        up = lambda a, b: F.interpolate(a, size=b.shape[-2:], mode="bilinear", align_corners=False)  # noqa: E731
        d = self.d4(torch.cat([up(e4, e3), e3], 1))
        d = self.d3(torch.cat([up(d, e2), e2], 1))
        d = self.d2(torch.cat([up(d, e1), e1], 1))
        d = self.d1(torch.cat([up(d, s), s], 1))
        return F.interpolate(self.head(d), size=x.shape[-2:], mode="bilinear", align_corners=False)
