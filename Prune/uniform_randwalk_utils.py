import random
import copy
import torch
import numpy as np
from Prune import Utils

def generate_masks(model):
    weight_masks = []
    for p in model.parameters():
        if len(p.data.size()) != 1:
            retained_inds = p.data.abs() > 0
            weight_masks.append(retained_inds.float())

    bias_masks = []
    for i in range(len(weight_masks)):
        mask = torch.ones(len(weight_masks[i]))
        for j in range(len(weight_masks[i])):
            if torch.sum(weight_masks[i][j]) == 0:
                mask[j] = torch.tensor(0.0)
        bias_masks.append(mask)
    return weight_masks, bias_masks

def select_seed_unit(mask, robin_unit = -1, forward = True, round_robin = False):
    seed_unit = None
    if forward:
        length = mask[0].shape[1]
    elif not forward:
        length = mask[-1].shape[0]
    if not round_robin:
        seed_unit = random.choice(list(range(length)))
    elif round_robin:
        if robin_unit < length - 1:
            seed_unit = robin_unit + 1
        else:
            seed_unit = 0
    return seed_unit

def sum_masks(mask):
    num = 0
    for i in range(len(mask)):
        num = num + torch.sum(mask[i])
    return num

def get_param_options(mask, prev_unit, forward,  allow_retrace = True):
    if forward:
        idx_options1 = list(range(mask.shape[0]))
        idx_options2 = prev_unit
        idx_options3 = list(range(mask.shape[2]))
        idx_options4 = list(range(mask.shape[3]))
        return random.choice(idx_options1), idx_options2, random.choice(idx_options3), random.choice(idx_options4), mask.shape[0]
    elif not forward:
        idx_options1 = prev_unit
        idx_options2 = list(range(mask.shape[1]))
        idx_options3 = list(range(mask.shape[2]))
        idx_options4 = list(range(mask.shape[3]))

        return idx_options1, random.choice(idx_options2), random.choice(idx_options3), random.choice(idx_options4)

def get_unit_options(mask, prev_unit, forward = True, allow_retrace = True):
    if forward:
        idx_options = list(range(mask.shape[0]))
        return random.choice(idx_options),prev_unit

    elif not forward:
        idx_options = list(range(mask.shape[1]))
        return prev_unit, random.choice(idx_options), mask.shape[1]


def conv_to_linear_unit(mask, prev_unit, conv_length, linear_length, forward):
    if forward:
        idx = random.choice(list(range(int(mask.shape[1]/conv_length))))
        idx = idx + int(mask.shape[1]/conv_length)*prev_unit
        return idx
    elif not forward:
        factor = int(linear_length/conv_length)
        idx = int(prev_unit/factor)
        return idx

def uniform_masks(network, prune_perc, weight_masks,bias_masks, verbose = True, kernel_conserved = False):
    net = copy.deepcopy(network)
    num = 0
    for p in net.parameters():
        p.data.fill_(0)
        if len(p.data.size()) != 1:
            num = num + 1
    num_weights = Utils.count_weights(network)
    num_weights = int((1 - prune_perc / 100.0) * num_weights)
    input_robin_unit = -1
    input_counter = np.zeros(weight_masks[0].shape[1])
    output_robin_unit = -1
    output_counter = np.zeros(weight_masks[-1].shape[0])
    i = 0

    while sum_masks(weight_masks) < num_weights:

        if i%2 == 0:

            conv_length = 0
            #prev_unit = select_seed_unit_counter(weight_masks, input_counter, forward=True)
            prev_unit = select_seed_unit(weight_masks, input_robin_unit, forward=True, round_robin=True)
            input_robin_unit = prev_unit
            input_counter[prev_unit] = input_counter[prev_unit] + 1
            ctol_flag = 0
            k = 0

            while k < len(weight_masks):

                if len(weight_masks[k].shape) == 4:
                    if k + 3 < len(weight_masks) and len(weight_masks[k+3].shape) == 4:
                        if weight_masks[k+3].shape[2] == 1:
                            k = k + random.choice([0,3])
                    #print(k)
                    idx1, idx2, idx3, idx4, conv_length = get_param_options(weight_masks[k], prev_unit,forward=True)
                    weight_masks[k][idx1, idx2, idx4, idx3 ] = 1
                    if kernel_conserved:
                        weight_masks[k][idx1, idx2].fill_(1)
                    bias_masks[k][idx1] = 1
                    prev_unit = idx1
                    ctol_flag = 1

                    if k + 1 < len(weight_masks) and len(weight_masks[k+1].shape) == 4:
                        if weight_masks[k + 1].shape[2] == 1:
                            k = k + 1
                    #else:
                    k = k + 1
                    #print(k,'shreyas')

                elif len(weight_masks[k].shape) == 2:
                    if ctol_flag == 1:
                        prev_unit = conv_to_linear_unit(weight_masks[k], prev_unit, conv_length, 0, forward=True)
                        ctol_flag = 0
                    idx1, idx2 = get_unit_options(weight_masks[k], prev_unit, forward=True)
                    weight_masks[k][idx1, idx2] = 1
                    bias_masks[k][idx1] = 1
                    prev_unit = idx1
                    if k == num-1:
                        output_counter[prev_unit] = output_counter[prev_unit] + 1
                    k = k + 1

        else:

            prev_unit = select_seed_unit(weight_masks, output_robin_unit, forward=False, round_robin=True)
            output_robin_unit = prev_unit
            output_counter[prev_unit] = output_counter[prev_unit] + 1
            ltoc_flag = 0
            linear_length = 0
            k = 0

            while k < len(weight_masks):

                if len(weight_masks[num - k - 1].shape) == 2:
                    idx1, idx2, linear_length = get_unit_options(weight_masks[num-k-1], prev_unit,forward=False)
                    weight_masks[num - k - 1][idx1, idx2] = 1
                    bias_masks[num - k - 1][idx1] = 1
                    prev_unit = idx2
                    ltoc_flag = 1
                    k = k + 1

                elif len(weight_masks[num-k-1].shape) == 4:

                    if ltoc_flag == 1:
                        prev_unit = conv_to_linear_unit(weight_masks[num-k-1], prev_unit, conv_length, linear_length, forward = False)
                        ltoc_flag = 0

                    if weight_masks[num - k - 1].shape[2] == 1:
                        k = k + random.choice([0,1])

                    idx1, idx2, idx3, idx4 = get_param_options(weight_masks[num - k - 1], prev_unit,forward=False)
                    weight_masks[num - k - 1][idx1, idx2, idx4, idx3] = 1
                    if kernel_conserved:
                        weight_masks[num - k - 1][idx1, idx2].fill_(1)
                    bias_masks[num - k - 1][idx1] = 1
                    prev_unit = idx2
                    if k == num-1:
                        input_counter[prev_unit] = input_counter[prev_unit] + 1

                    if weight_masks[num - k - 1].shape[2] == 1:
                        k = k + 3
                    else:
                        k = k + 1

        i = i + 1
        if verbose:
            print(f'Enabled Weights: {sum_masks(weight_masks)},' \
                  + f'\tTarget Weights: {num_weights}', end="\r", flush=True)
    Utils.ratio(network, weight_masks)
    return weight_masks, bias_masks