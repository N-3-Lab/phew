import torch
import torch.nn as nn
from Utils import load
from Utils import train
from Prune import mag_utils
import copy
import pickle as pkl


def run(args):
    torch.manual_seed(args.seed)
    dev = load.device(args.gpu)

    input_shape, num_classes = load.dimension(args.dataset)
    train_loader = load.dataloader(args.dataset, args.train_batch_size, True, args.workers)
    test_loader = load.dataloader(args.dataset, args.train_batch_size, False, args.workers)

    model = load.model(args.model, args.dataset)(input_shape, num_classes).to(dev)

    if args.pre_epochs > 0:

        loss = nn.CrossEntropyLoss()
        opt, opt_kwargs = load.optimizer(args.optimizer)

        optimizer = opt(model.parameters(), lr=args.lr, weight_decay=args.weight_decay, **opt_kwargs)
        scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones=args.lr_drops, gamma=args.lr_drop_rate)

        model = train.train_mag(model, loss, optimizer, train_loader,test_loader, dev, args.pre_epochs, scheduler)


    for i in range(len(args.prune_perc)):
        print(args.experiment, str(args.prune_perc[len(args.prune_perc) - i - 1]), str(args.model), str(args.dataset))

        prune_perc = args.prune_perc[len(args.prune_perc)-i-1]
        sparse_model = copy.deepcopy(model)
        loss = nn.CrossEntropyLoss()
        opt, opt_kwargs = load.optimizer(args.optimizer)

        if args.prune_iterations > 0:

            optimizer = opt(sparse_model.parameters(), lr=args.lr, weight_decay=args.weight_decay, **opt_kwargs)
            (sparse_model,weight_masks, bias_masks) = train.train_mag2(sparse_model, loss, optimizer, train_loader,
                                                                        test_loader, dev, args.prune_iterations, prune_perc)

        else:
            weight_masks, bias_masks = mag_utils.mag_prune_masks(sparse_model, prune_perc, dev)

        sparse_model.set_masks(weight_masks, bias_masks)
        sparse_model.to(dev)
        optimizer = opt(sparse_model.parameters(), lr=args.lr, weight_decay=args.weight_decay, **opt_kwargs)
        scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones=args.lr_drops, gamma=args.lr_drop_rate)
        (net, train_curve, test_loss, accuracy1, accuracy5) = train.train(sparse_model, loss, optimizer, train_loader,
                                                                          test_loader, dev, args.epochs, scheduler)

        results = []

        results.append(train_curve)
        results.append(test_loss)
        results.append(accuracy1)
        results.append(accuracy5)

        with open(args.experiment + str(args.prune_perc[len(args.prune_perc)-i-1]) + str(args.model) + str(args.dataset) +str(args.seed)+ '.pkl', "wb") as fout:
            pkl.dump(results, fout, protocol=pkl.HIGHEST_PROTOCOL)