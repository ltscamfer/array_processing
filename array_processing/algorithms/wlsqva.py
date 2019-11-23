import numpy as np


def wlsqva(data, rij, hz, wgt=None):
    """
    Weighted least squares solution for slowness of a plane wave crossing
    an array of sensors

    This function estimates the slowness vector associated with a signal
    passing across an array of sensors under the model assumption that the
    wavefront is planar and the sensor locations are known exactly. The
    slowness is estimated directly from the sensor traces and position
    coordinates. Weights may be applied to each trace to either deselect a
    trace or (de)emphasize its contribution to the least squares solution.

    Args:
        data : array
            (m, n) time series with `m` samples from `n` traces as columns
        rij : array
            (d, n) `n` sensor coordinates as [northing, easting, {elevation}]
            column vectors in `d` dimensions
        hz : float or int
            sample rate
        wgt : list or array
            optional list|vector of relative weights of length `n`
            (0 == exclude trace). Default is None (use all traces with equal
            relative weights).

    Returns:
        vel : float
            signal velocity across array
        az : float or array
            `d = 2`: back azimuth (float) from co-array coordinate origin (º CW
            from N); `d = 3`: back azimuth and elevation angle (array) from
            co-array coordinate origin (º CW from N, º from N-E plane)
        tau : array
            (n(n-1)//2, ) time delays of relative signal arrivals (TDOA) for all
            unique sensor pairings
        cmax : array
            (n(n-1)//2, ) cross-correlation maxima (e.g., for use in MCCMcalc) for
            each sensor pairing in `tau`
        sig_tau : float
            uncertainty estimate for `tau`, also estimate of plane wave model
            assumption violation for non-planar arrivals
        s : array
            (d, ) signal slowness vector via generalized weighted least squares
        xij : array
            (d, n(n-1)//2) co-array, coordinates of the sensor pairing separations

    Raises
    ~~~~~~
    ValueError
        If the input arguments are not consistent with least squares.
    IndexError
        If the input argument dimensions are not consistent.

    Notes
    ~~~~~
    Typical use provides sensor coordinates in km and sample rate in Hz.  This
    will give `vel` in km/s and `s` in s/km; `az` is always in º; `sig_tau`
    and `tau` in s; `xij` in km.

    Cross-correlation maxima in `cij` are normalized to unity for auto-
    correlations at zero lag and set to zero for any pairing with a zero-
    weight trace.

    For a 2D array, a minimum of 3 sensors are required; for 3D, 4 sensors.
    The `data` and `rij` must have a consistent number of sensors. If provided,
    `wgt` must be consistent with the number of sensors.

    Examples
    ~~~~~~~~
    Given an approppriate (m, 4) array ``data``, sampled at 20 Hz, the
    following would estimate the slowness using the entire array.

    >>> rij = np.array([[0, 1, 0.5, 0], [1, 0, 0.5, -1]])
    >>> vel, az, tau, cmax, sig_tau, s, xij = wlsqva(data, rij, 20)

    To eliminate the 3d trace from the slowness  estimation, a ``wgt`` list
    can be passed as an argument.

    >>> wgt = [1, 1, 0, 1]
    >>> vel, az, tau, cmax, sig_tau, s, xij = wlsqva(data, rij, 20, wgt)

    Similarly, if the 3d trace is suspect, but should not be completely removed
    from the slowness estimation, it can be given a smaller, relative, weight
    to the other traces.

    >>> wgt = [1, 1, 0.3, 1]
    >>> vel, az, tau, cmax, sig_tau, s, xij = wlsqva(data, rij, 20, wgt)

    Often, only `vel`, `az` are required, so the other returns may be combined
    with extended sequence unpacking in Python 3.X.

    >>> vel, az, *aux_vars = wlsqva(data, rij, 20)

    """

    # -- input error checking cell (no type checking, just dimensions to help
    #    user identify the problem)
    if data.shape[1] != rij.shape[1]:
        raise IndexError('data.shape[1] != ' + str(rij.shape[1]))
    if rij.shape[1] < rij.shape[0]+1:
        raise ValueError('rij.shape[1] < ' + str(rij.shape[0]+1))
    if rij.shape[0] < 2 or rij.shape[0] > 3:
        raise ValueError('rij.shape[0] != 2|3')
    # --

    # size things up
    m, nTraces = data.shape  # number of samples & stations
    dim = rij.shape[0]   # 2D or 3D array?
    # set default wgt, recast as an array, form W array
    if wgt is None:
        # all ones (any constant will do)
        wgt = np.array([1 for i in range(nTraces)])
        N_w = nTraces
        # -- no need for an error check since all channels kept
    else:
        wgt = np.array(wgt)
        # -- error checks on wgt done here since now in array form
        if len(wgt) != nTraces:
            raise IndexError('len(wgt) != ' + str(nTraces))
        N_w = sum(wgt != 0)
        if N_w < dim+1:
            raise ValueError('sum(wgt != 0) < ' + str(dim+1))
        # --

    # very handy list comprehension for array processing
    idx = [(i, j, wgt[i]*wgt[j]) for i in range(rij.shape[1]-1)
           for j in range(i+1, rij.shape[1])]
    # -- co-array is now a one-liner
    xij = rij[:, [i[0] for i in idx]] - rij[:, [j[1] for j in idx]]
    # -- same for generalized weight array
    W = np.diag([i[2] for i in idx])
    # compute cross correlations across co-array
    N = xij.shape[1]           # number of unique inter-sensor pairs
    cij = np.empty((m * 2 - 1, N))    # pre-allocated cross-correlation matrix
    for k in range(N):
        # MATLAB's xcorr w/ 'coeff' normalization: unit auto-correlations
        # and save a little time by only calculating on weighted pairs
        if W[k][k]:
            cij[:, k] = (np.correlate(data[:, idx[k][0]], data[:, idx[k][1]],
                                      mode='full') / np.sqrt(sum(data[:, idx[k][0]] * data[:, idx[k][0]]) * sum(data[:, idx[k][1]]*data[:, idx[k][1]])))

    # extract cross correlation maxima and associated delays
    cmax = cij.max(axis=0)
    cmax[[i for i in range(N) if W[i][i] == 0]] = 0  # set to zero if not Wvec
    delay = np.argmax(cij, axis=0) + 1 # MATLAB-esque +1 offset here for tau
    # form tau vector
    tau = (m - delay)/hz
    # form auxiliary arrays for general weighted LS
    X_p = W@xij.T
    tau_p = W@tau

    # calculate least squares slowness vector
    s_p = np.linalg.inv(X_p.T@X_p) @ X_p.T @ tau_p
    # re-cast slowness as geographic vel, az (and phi, if req'd)
    vel = 1/np.linalg.norm(s_p, 2)
    # this converts az from mathematical CCW from E to geographical CW from N
    az = (np.arctan2(s_p[0], s_p[1]) * 180 / np.pi - 360) % 360
    if dim == 3:
        # if 3D, tack on elevation angle to azimuth
        az = np.hstack((az, np.arctan2(s_p[2], np.linalg.norm(s_p[:2], 2)) * 180 / np.pi))

    # calculate sig_tau (note: moved abs function inside sqrt so that std.
    # np.sqrt can be used; only relevant in 3D case w nearly singular
    # solutions, where argument of sqrt is small, but negative)
    N_p = N_w*(N_w-1)/2
    sig_tau_p = np.sqrt(np.abs(tau_p @ (np.eye(N) - X_p @ np.linalg.inv(X_p.T @ X_p) @ X_p.T) @       tau_p / (N_p - dim)))

    return vel, az, tau_p, cmax, sig_tau_p, s_p, xij