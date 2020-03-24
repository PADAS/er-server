from math import radians, cos, sin, asin, sqrt


def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in km
    return c * r


def dbscan(dataset, eps, min_cluster_size):
    """
    https://en.wikipedia.org/wiki/DBSCAN

    :param dataset: input data/alerts to cluster
    :param eps: distance beyond which 2 features can not belong to the same cluster
    :param min_cluster_size: minimum number of features to generate a cluster
    :return: a list of cluster labels
    """

    # Initially all labels are 0.
    # 0 - Means the point hasn't been considered yet.
    labels = [0] * len(dataset)

    current_cluster = 0

    # This outer loop is just responsible for picking new seed points--a point
    # from which to grow a new cluster.
    # Once a valid seed point is found, a new cluster is created, and the
    # cluster growth is all handled by the 'grow_cluster' function.

    # For each point p in the dataset ...
    # ('p' is the index of the datapoint, rather than the data point itself.)
    for p in range(0, len(dataset)):

        # Only points that have not already been claimed can be picked as new
        # seed points.
        # If the point's label is not 0, continue to the next point.
        if not (labels[p] == 0):
            continue

        # Find all of P's neighboring points.
        neighbor_pts = radius_query(dataset, p, eps)

        # If the number is below min_cluster_size, this point is noise.
        # This is the only condition under which a point is labeled
        # NOISE--when it's not a valid seed point. A NOISE point may later
        # be picked up by another cluster as a boundary point (this is the only
        # condition under which a cluster label can change--from NOISE to
        # something else).
        if len(neighbor_pts) < min_cluster_size:
            labels[p] = -1
        # Otherwise, if there are at least MinPts nearby, use this point as the
        # seed for a new cluster.
        else:
            current_cluster += 1
            grow_cluster(dataset, labels, p, neighbor_pts, current_cluster, eps, min_cluster_size)

    # All data has been clustered!
    return labels


def grow_cluster(dataset, labels, p, neighbor_pts, current_cluster, eps, min_cluster_size):
    """
    Grow a new cluster from the seed point `p`.

    This function searches through the dataset to find all points that belong to
    this new cluster. When this function returns, current_cluster is complete.

    :param dataset:
    :param labels: list storing the cluster labels for all dataset points
    :param p: Index of the seed point for this new cluster
    :param neighbor_pts: All of the neighbors of `p`
    :param current_cluster: the label for this new cluster
    :param eps: distance beyond which 2 features can not belong to the same cluster
    :param min_cluster_size:
    :return:
    """

    # Assign the cluster label to the seed point.
    labels[p] = current_cluster

    # Look at each neighbor of p (neighbors are referred to as pn).
    # neighbor_pts will be used as a queue of points to search--that is, it
    # will grow as we discover new core points for the cluster.
    # In neighbor_pts, the points are represented by their index in the original
    # dataset.
    i = 0
    while i < len(neighbor_pts):

        # Get the next point from the queue.
        pn = neighbor_pts[i]

        # If pn was labelled NOISE during the seed search, then we
        # know it's not a core point (it doesn't have enough neighbors), so
        # make it a border point of the current_cluster and move on.
        if labels[pn] == -1:
            labels[pn] = current_cluster

        # Otherwise, if pn isn't already claimed,
        # claim it as part of current_cluster.
        elif labels[pn] == 0:
            # Add pn to the current cluster.
            labels[pn] = current_cluster

            # Find all the neighbors of pn
            pn_neighbor_pts = radius_query(dataset, pn, eps)

            # If pn has at least min_cluster_size neighbors, it's a core point!
            # Add all of its neighbors to the FIFO queue to be searched.
            if len(pn_neighbor_pts) >= min_cluster_size:
                neighbor_pts = neighbor_pts + pn_neighbor_pts
            # If pn *doesn't* have enough neighbors, then it's a border point.
            # Don't queue up it's neighbors as expansion points.
            # else Do nothing

        # Advance to the next point in the queue.
        i += 1


def radius_query(dataset, p, eps):
    """
    Find all points in the dataset  within distance `eps` of point `p`.
    :param dataset:
    :param p: index of data point in the dataset
    :param eps: distance beyond which 2 features can not belong to the same cluster
    :return:
    """
    neighbors = []

    # For each point in the dataset...
    current_point = dataset[p]
    for pn in range(0, len(dataset)):
        point = dataset[pn]

        try:
            distance_apart = haversine(current_point['longitude'], current_point['latitude'], point['longitude'], point['latitude'])

            if distance_apart < eps:
                neighbors.append(pn)

        except KeyError:
            pass

    return neighbors

# [1,1,2,1,2,2,3,1]
def group_alerts(dataset, labels):
    unique_labels_dict = {label: [] for label in labels if label > 0}
    for lbl, alert in zip(labels, dataset):
        unique_labels_dict[lbl].append(alert)

    return [v for v in unique_labels_dict.values()]


def normalize_alert_object(alert):
    if isinstance(alert, dict):
        if 'lat' in alert:
            alert['latitude'] = alert.pop('lat')
        if 'long' in alert:
            alert['longitude'] = alert.pop('long')

    return alert


def cluster_alerts(alerts, radius, min_cluster_size):
    normalized_alerts = [normalize_alert_object(alert) for alert in alerts]
    labels = dbscan(normalized_alerts, radius, min_cluster_size)
    clustered_alerts = group_alerts(normalized_alerts, labels)
    # pick a random(the first alert) in a cluster
    # could also get the center of the points in the cluster?
    result = []
    for i in clustered_alerts:
        random_alert = i[0]
        random_alert['num_clustered_alerts'] = len(i)
        result.append(random_alert)
    return result







