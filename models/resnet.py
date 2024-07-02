'''ResNet in PyTorch.
BasicBlock and Bottleneck module is from the original ResNet paper:
[1] Kaiming He, Xiangyu Zhang, Shaoqing Ren, Jian Sun
    Deep Residual Learning for Image Recognition. arXiv:1512.03385
PreActBlock and PreActBottleneck module is from the later paper:
[2] Kaiming He, Xiangyu Zhang, Shaoqing Ren, Jian Sun
    Identity Mappings in Deep Residual Networks. arXiv:1603.05027
'''
import torch
import torch.nn as nn
import torch.nn.functional as F

from models.base_model import BaseModel
from models.transform_layers import NormalizeLayer
from torch.nn.utils import spectral_norm
from torchvision import models
import random

def conv3x3(in_planes, out_planes, stride=1):
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_planes, planes, stride=1, activation=F.relu):
        super(BasicBlock, self).__init__()
        self.conv1 = conv3x3(in_planes, planes, stride)
        self.conv2 = conv3x3(planes, planes)
        self.bn1 = nn.BatchNorm2d(planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.activation = activation

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion*planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, self.expansion*planes, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(self.expansion*planes)
            )

    def forward(self, x):
        out = self.activation(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        out = self.activation(out)
        return out


class PreActBlock(nn.Module):
    '''Pre-activation version of the BasicBlock.'''
    expansion = 1

    def __init__(self, in_planes, planes, stride=1, activation=F.relu):
        super(PreActBlock, self).__init__()
        self.conv1 = conv3x3(in_planes, planes, stride)
        self.conv2 = conv3x3(planes, planes)
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.activation = activation

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion*planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, self.expansion*planes, kernel_size=1, stride=stride, bias=False)
            )

    def forward(self, x):
        out = self.activation(self.bn1(x))
        shortcut = self.shortcut(out)
        out = self.conv1(out)
        out = self.conv2(self.activation(self.bn2(out)))
        out += shortcut
        return out


class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, in_planes, planes, stride=1, activation=F.relu):
        super(Bottleneck, self).__init__()
        self.conv1 = nn.Conv2d(in_planes, planes, kernel_size=1, bias=False)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.conv3 = nn.Conv2d(planes, self.expansion*planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.bn3 = nn.BatchNorm2d(self.expansion * planes)
        self.activation = activation

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion*planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, self.expansion*planes, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(self.expansion*planes)
            )

    def forward(self, x):
        out = self.activation(self.bn1(self.conv1(x)))
        out = self.activation(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        out += self.shortcut(x)
        out = self.activation(out)
        return out


class PreActBottleneck(nn.Module):
    '''Pre-activation version of the original Bottleneck module.'''
    expansion = 4

    def __init__(self, in_planes, planes, stride=1, activation=F.relu):
        super(PreActBottleneck, self).__init__()
        self.conv1 = nn.Conv2d(in_planes, planes, kernel_size=1, bias=False)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.conv3 = nn.Conv2d(planes, self.expansion*planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.bn3 = nn.BatchNorm2d(planes)
        self.activation = activation

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion*planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, self.expansion*planes, kernel_size=1, stride=stride, bias=False)
            )

    def forward(self, x):
        out = self.activation(self.bn1(x))
        shortcut = self.shortcut(out)
        out = self.conv1(out)
        out = self.conv2(self.activation(self.bn2(out)))
        out = self.conv3(self.activation(self.bn3(out)))
        out += shortcut
        return out


class ResNet(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10, activation="relu"):
        last_dim = 512 * block.expansion
        super(ResNet, self).__init__(last_dim, num_classes)
        

        if activation=='gelu':
            self.activation = F.gelu
        else:
            self.activation = F.relu
        
        self.in_planes = 64
        self.last_dim = last_dim

        self.normalize = NormalizeLayer()

        self.conv1 = conv3x3(3, 64)
        self.bn1 = nn.BatchNorm2d(64)

        self.layer1 = self._make_layer(block, 64, num_blocks[0], stride=1)
        self.layer2 = self._make_layer(block, 128, num_blocks[1], stride=2)
        self.layer3 = self._make_layer(block, 256, num_blocks[2], stride=2)
        self.layer4 = self._make_layer(block, 512, num_blocks[3], stride=2)

    def _make_layer(self, block, planes, num_blocks, stride):
        strides = [stride] + [1]*(num_blocks-1)
        layers = []
        for stride in strides:
            layers.append(block(self.in_planes, planes, stride, self.activation))
            self.in_planes = planes * block.expansion
        return nn.Sequential(*layers)

    def penultimate(self, x, all_features=False):
        out_list = []

        out = self.normalize(x)
        out = self.conv1(out)
        out = self.bn1(out)
        out = self.activation(out)
        out_list.append(out)

        out = self.layer1(out)
        out_list.append(out)
        out = self.layer2(out)
        out_list.append(out)
        out = self.layer3(out)
        out_list.append(out)
        out = self.layer4(out)
        out_list.append(out)

        out = F.avg_pool2d(out, 4)
        out = out.view(out.size(0), -1)

        if all_features:
            return out, out_list
        else:
            return out

class Pretrain_ResNet(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10):
        last_dim = 512 * block.expansion
        super(Pretrain_ResNet, self).__init__(last_dim, num_classes)

        self.in_planes = 64
        self.last_dim = last_dim

        mu = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda()
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()
        self.norm = lambda x: (x - mu) / std
        self.backbone = models.resnet18(pretrained=True)
        self.backbone.fc = torch.nn.Identity()
        i = 0
        num = 30
        for param in self.backbone.parameters():
            if i<num:
                param.requires_grad = False
            i+=1
        #self.backbone =models.resnet18(pretrained=False)
        #checkpoint = torch.load("./resnet18_linf_eps8.0.ckpt")
        #state_dict_path = 'model'
        #sd = checkpoint[state_dict_path]
        #sd = {k[len('module.'):]:v for k,v in sd.items()}
        #sd_t = {k[len('attacker.model.'):]:v for k,v in sd.items() if k.split('.')[0]=='attacker' and k.split('.')[1]!='normalize'}
        #self.backbone.load_state_dict(sd_t)        
        #self.backbone.fc = torch.nn.Identity()        
        # freeze_parameters(self.backbone, backbone, train_fc=False)

    def penultimate(self, x, all_features=False):
        x = self.norm(x)
        z1 = self.backbone(x)
        z_n = F.normalize(z1, dim=-1)
        return z_n


class Pretrain_ResNet18_Corruption(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10, std=1.0, mean=0.0, noise_scale=0.1, probability=0.5):
        last_dim = 512 * block.expansion
        super(Pretrain_ResNet18_Corruption, self).__init__(last_dim, num_classes)

        self.in_planes = 64
        self.last_dim = last_dim

        mu = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda()
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()
        self.norm = lambda x: (x - mu) / std
        self.backbone = models.resnet18(pretrained=True)
        self.backbone.fc = torch.nn.Identity()
        i = 0
        num = 30
        for param in self.backbone.parameters():
            if i<num:
                param.requires_grad = False
            i+=1
        self.std = std
        self.mean = mean
        self.noise_scale = noise_scale
        self.device = torch.device(f"cuda" if torch.cuda.is_available() else "cpu")
        self.probability = probability

    def penultimate(self, x, all_features=False):
        p = random.random()
        if p < self.probability:
            x = x + (torch.randn(x.size()).to(self.device) * self.std + self.mean)*self.noise_scale
        x = self.norm(x)
        z1 = self.backbone(x)
        z_n = F.normalize(z1, dim=-1)
        return z_n


class Pretrain_ResNet152(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10):
        last_dim = 2048 * block.expansion
        super(Pretrain_ResNet152, self).__init__(last_dim, num_classes)

        self.in_planes = 64
        self.last_dim = last_dim

        mu = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda()
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()
        self.norm = lambda x: (x - mu) / std
        self.backbone = models.resnet152(pretrained=True)
        self.backbone.fc = torch.nn.Identity()
        i = 0
        num = 108
        for param in self.backbone.parameters():
            if i<num:
                param.requires_grad = False
            i+=1

    def penultimate(self, x, all_features=False):
        x = self.norm(x)
        z1 = self.backbone(x)
        z_n = F.normalize(z1, dim=-1)
        return z_n


class Pretrain_Wide_ResNet(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10):
        last_dim = 2048 * block.expansion
        super(Pretrain_Wide_ResNet, self).__init__(last_dim, num_classes)

        self.in_planes = 64
        self.last_dim = last_dim

        mu = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda()
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()
        self.norm = lambda x: (x - mu) / std
        self.backbone = models.wide_resnet50_2(pretrained=True)
        self.backbone.fc = torch.nn.Identity()
        i = 0
        num = 72
        for param in self.backbone.parameters():
            if i<num:
                param.requires_grad = False
            i+=1

    def penultimate(self, x, all_features=False):
        x = self.norm(x)
        z1 = self.backbone(x)
        z_n = F.normalize(z1, dim=-1)
        return z_n


class Pretrain_ResNet152_Corruption(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10):
        last_dim = 2048 * block.expansion
        super(Pretrain_ResNet152_Corruption, self).__init__(last_dim, num_classes)
        from robustbench.utils import load_model

        self.in_planes = 64
        self.last_dim = last_dim
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        
        mu = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda()
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()
        self.norm = lambda x: (x - mu) / std
        self.backbone = load_model('Hendrycks2020Many', dataset='imagenet', threat_model='corruptions').to(device)
        self.backbone.model.fc = torch.nn.Identity()
        i = 0
        num = 108
        for param in self.backbone.parameters():
            if i<num:
                param.requires_grad = False
            i+=1

    def penultimate(self, x, all_features=False):
        x = self.norm(x)
        z1 = self.backbone(x)
        z_n = F.normalize(z1, dim=-1)
        return z_n


class Pretrain_ConvNext(BaseModel):
    def __init__(self, block, num_blocks, num_classes=10):
        last_dim = 1024 * block.expansion
        super(Pretrain_ConvNext, self).__init__(last_dim, num_classes)
    
        self.in_planes = 64
        self.last_dim = last_dim
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        
        mu = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1).cuda()
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1).cuda()
        self.norm = lambda x: (x - mu) / std
        self.backbone = models.convnext_base(pretrained=True)
        self.backbone.classifier = torch.nn.Identity()
        
        i = 0
        num = 260
        for param in self.backbone.parameters():
            if i<num:
                param.requires_grad = False
            i+=1

    def penultimate(self, x, all_features=False):
        x = self.norm(x)
        z1 = self.backbone(x)
        z1 = z1.reshape(-1, 1024)
        z_n = F.normalize(z1, dim=-1)
        return z_n


def ResNet18(num_classes, activation=None):
    return ResNet(BasicBlock, [2,2,2,2], num_classes=num_classes, activation=activation)

def ResNet34(num_classes):
    return ResNet(BasicBlock, [3,4,6,3], num_classes=num_classes)

def ResNet50(num_classes):
    return ResNet(Bottleneck, [3,4,6,3], num_classes=num_classes)

def Pretrain_ResNet18_Model(num_classes):
    return Pretrain_ResNet(BasicBlock, [2,2,2,2],   num_classes=num_classes)

def Pretrain_ResNet152_Model(num_classes):
    return Pretrain_ResNet152(BasicBlock, [2,2,2,2], num_classes=num_classes)


def Pretrain_Wide_ResNet_Model(num_classes):
    return Pretrain_Wide_ResNet(BasicBlock, [2,2,2,2], num_classes=num_classes)

def Pretrain_ResNet152_Corruption_Model(num_classes):
    return Pretrain_ResNet152_Corruption(BasicBlock, [2,2,2,2], num_classes=num_classes)

def Pretrain_ResNet18_Corruption_Model(num_classes, std=1.0, mean=0.0, noise_scale=0.1, probability=0.5):
    return Pretrain_ResNet18_Corruption(BasicBlock, [2,2,2,2], num_classes=num_classes, std=std, mean=mean, noise_scale=noise_scale, probability=probability)


def Pretrain_ConvNext_Model(num_classes):
    return Pretrain_ConvNext(BasicBlock, [2,2,2,2], num_classes=num_classes)
