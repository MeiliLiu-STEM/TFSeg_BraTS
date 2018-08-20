import tensorflow as tf
import numpy as np

FLAGS = tf.app.flags.FLAGS


def unpool_with_argmax(pool, ind, name=None, ksize=[1, 2, 2, 1]):
    """
       Unpooling layer after max_pool_with_argmax.
       Args:
           pool:   max pooled output tensor
           ind:      argmax indices
           ksize:     ksize is the same as for the pool
       Return:
           unpool:    unpooling tensor
    """
    tmp_batch_size = FLAGS.batch_size
    with tf.variable_scope(name):
        input_shape = pool.get_shape().as_list()
        output_shape = (tmp_batch_size,
                        input_shape[1] * ksize[1],
                        input_shape[2] * ksize[2],
                        input_shape[3])

        flat_input_size = np.prod(input_shape[1:]) * tmp_batch_size
        flat_output_shape = [output_shape[0],
                             output_shape[1] * output_shape[2] * output_shape[3]]

        pool_ = tf.reshape(pool, [flat_input_size])
        batch_range = tf.reshape(tf.range(output_shape[0], dtype=ind.dtype),
                                 shape=[tmp_batch_size, 1, 1, 1])

        b = tf.ones_like(ind) * batch_range
        b = tf.reshape(b, [flat_input_size, 1])
        ind_ = tf.reshape(ind, [flat_input_size, 1])
        ind_ = tf.concat([b, ind_], 1)

        ret = tf.scatter_nd(ind_, pool_, shape=flat_output_shape)
        ret = tf.reshape(ret, output_shape)
        return ret


def conv_classifier(input_layer, initializer):
    # output predicted class number (2)
    with tf.variable_scope('conv_classifier') as scope:  # all variables prefixed with "conv_classifier/"
        shape = [1, 1, 64, FLAGS.num_class]
        kernel = _variable_with_weight_decay('weights', shape=shape, initializer=initializer, wd=None)
        #kernel = tf.get_variable('weights', shape, initializer=initializer)
        conv = tf.nn.conv2d(input_layer, filter=kernel, strides=[1, 1, 1, 1], padding='SAME')
        biases = _variable_on_cpu('biases', [FLAGS.num_class], tf.constant_initializer(0.0))
        conv_classifier = tf.nn.bias_add(conv, biases, name=scope.name)
    return conv_classifier


def conv_layer_with_bn(initializer, inputT, shape, is_training, activation=True, name=None):
    in_channel = shape[2]
    out_channel = shape[3]
    k_size = shape[0]

    with tf.variable_scope(name) as scope:
        kernel = _variable_with_weight_decay('weights', shape=shape, initializer=initializer, wd=None)
        #kernel = tf.get_variable(scope.name, shape, initializer=initializer)
        conv = tf.nn.conv2d(inputT, kernel, [1, 1, 1, 1], padding='SAME')
        biases = tf.Variable(tf.constant(0.0, shape=[out_channel], dtype=tf.float32),
                             trainable=True, name='biases')
        bias = tf.nn.bias_add(conv, biases)

        if activation is True:  # only use relu during encoder
            conv_out = tf.nn.relu(batch_norm_layer(bias, is_training, scope.name))
        else:
            conv_out = batch_norm_layer(bias, is_training, scope.name)
    return conv_out


def batch_norm_layer(inputT, is_training, scope):
    return tf.cond(is_training,
                   lambda: tf.contrib.layers.batch_norm(inputT, is_training=True,
                                                        center=False, decay=FLAGS.moving_average_decay, scope=scope),
                   lambda: tf.contrib.layers.batch_norm(inputT, is_training=False,
                                                        center=False, reuse=True, decay=FLAGS.moving_average_decay, scope=scope))


def _variable_with_weight_decay(name, shape, initializer, wd):
    """ Helper to create an initialized Variable with weight decay.
        Note that the Variable is initialized with a truncated normal distribution.
        A weight decay is added only if one is specified.
    Args:
        name: name of the variable
        shape: list of ints
        stddev: standard deviation of a truncated Gaussian
        wd: add L2Loss weight decay multiplied by this float. If None, weight
            decay is not added for this Variable.
    Returns:
        Variable Tensor
    """
    var = _variable_on_cpu(name, shape, initializer)

    if wd is not None:
        weight_decay = tf.multiply(tf.nn.l2_loss(var), wd, name='weight_loss')
        tf.add_to_collection('losses', weight_decay)
    return var


def _variable_on_cpu(name, shape, initializer):
    """Helper to create a Variable stored on CPU memory.
    Args:
        name: name of the variable
        shape: list of ints
        initializer: initializer for Variable
    Returns:
        Variable Tensor
    """
    with tf.device('/cpu:0'):
        # dtype = tf.float16 if FLAGS.use_fp16 else tf.float32 #added this after, cause it was in cifar model
        var = tf.get_variable(name, shape, initializer=initializer)  # , dtype=dtype)
    return var


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++


def inference_basic(images, is_training):
    """
      Args:
        images: Images Tensors (placeholder with correct shape, img_h, img_w, img_d)
        is_training: If the model is training or testing
    """
    initializer = get_weight_initializer()
    img_d = images.get_shape().as_list()[3]
    norm1 = tf.nn.lrn(images, depth_radius=5, bias=1.0, alpha=0.0001, beta=0.75,
                      name='norm1')
    conv1 = conv_layer_with_bn(initializer, norm1, [7, 7, img_d, 64], is_training, name="conv1")
    pool1, pool1_indices = tf.nn.max_pool_with_argmax(conv1, ksize=[1, 2, 2, 1],
                                                      strides=[1, 2, 2, 1], padding='SAME', name='pool1')

    conv2 = conv_layer_with_bn(initializer, pool1, [7, 7, 64, 64], is_training, name="conv2")
    pool2, pool2_indices = tf.nn.max_pool_with_argmax(conv2, ksize=[1, 2, 2, 1],
                                                      strides=[1, 2, 2, 1], padding='SAME', name='pool2')

    conv3 = conv_layer_with_bn(initializer, pool2, [7, 7, 64, 64], is_training, name="conv3")
    pool3, pool3_indices = tf.nn.max_pool_with_argmax(conv3, ksize=[1, 2, 2, 1],
                                                      strides=[1, 2, 2, 1], padding='SAME', name='pool3')

    conv4 = conv_layer_with_bn(initializer, pool3, [7, 7, 64, 64], is_training, name="conv4")
    pool4, pool4_indices = tf.nn.max_pool_with_argmax(conv4, ksize=[1, 2, 2, 1],
                                                      strides=[1, 2, 2, 1], padding='SAME', name='pool4')

    """  End of encoder - starting decoder """

    unpool_4 = unpool_with_argmax(pool4, ind=pool4_indices, name='unpool_4')
    conv_decode4 = conv_layer_with_bn(initializer, unpool_4, [7, 7, 64, 64], is_training, False, name="conv_decode4")

    unpool_3 = unpool_with_argmax(conv_decode4, ind=pool3_indices, name='unpool_3')
    conv_decode3 = conv_layer_with_bn(initializer, unpool_3, [7, 7, 64, 64], is_training, False, name="conv_decode3")

    unpool_2 = unpool_with_argmax(conv_decode3, ind=pool2_indices, name='unpool_2')
    conv_decode2 = conv_layer_with_bn(initializer, unpool_2, [7, 7, 64, 64], is_training, False, name="conv_decode2")

    unpool_1 = unpool_with_argmax(conv_decode2, ind=pool1_indices, name='unpool_1')
    conv_decode1 = conv_layer_with_bn(initializer, unpool_1, [7, 7, 64, 64], is_training, False, name="conv_decode1")

    return conv_classifier(conv_decode1, initializer)


def inference_basic_dropout(images, is_training, keep_prob):
    """
      Args:
        images: Images Tensors (placeholder with correct shape, img_h, img_w, img_d)
        is_training: If the model is training or testing
        keep_prob = probability that the layer will be dropped (dropout layer active)
    """
    initializer = get_weight_initializer()
    img_d = images.get_shape().as_list()[3]
    norm1 = tf.nn.lrn(images, depth_radius=5, bias=1.0, alpha=0.0001, beta=0.75, name='norm1')

    conv1 = conv_layer_with_bn(initializer, norm1, [7, 7, img_d, 64], is_training, name="conv1")
    pool1, pool1_indices = tf.nn.max_pool_with_argmax(conv1, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool1')
    dropout1 = tf.layers.dropout(pool1, rate=(1 - keep_prob), training=is_training, name="dropout1")

    conv2 = conv_layer_with_bn(initializer, dropout1, [7, 7, 64, 64], is_training, name="conv2")
    pool2, pool2_indices = tf.nn.max_pool_with_argmax(conv2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool2')
    dropout2 = tf.layers.dropout(pool2, rate=(1 - keep_prob), training=is_training, name="dropout2")

    conv3 = conv_layer_with_bn(initializer, dropout2, [7, 7, 64, 64], is_training, name="conv3")
    pool3, pool3_indices = tf.nn.max_pool_with_argmax(conv3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool3')
    dropout3 = tf.layers.dropout(pool3, rate=(1 - keep_prob), training=is_training, name="dropout3")

    conv4 = conv_layer_with_bn(initializer, dropout3, [7, 7, 64, 64], is_training, name="conv4")
    pool4, pool4_indices = tf.nn.max_pool_with_argmax(conv4, ksize=[1, 2, 2, 1],
                                                      strides=[1, 2, 2, 1], padding='SAME', name='pool4')

    """  End of encoder - starting decoder """

    unpool_4 = unpool_with_argmax(pool4, ind=pool4_indices, name='unpool_4')
    conv_decode4 = conv_layer_with_bn(initializer, unpool_4, [7, 7, 64, 64], is_training, False, name="conv_decode4")

    decode_dropout3 = tf.layers.dropout(conv_decode4, rate=(1 - keep_prob), training=is_training, name="decoder_dropout3")
    unpool_3 = unpool_with_argmax(decode_dropout3, ind=pool3_indices, name='unpool_3')
    conv_decode3 = conv_layer_with_bn(initializer, unpool_3, [7, 7, 64, 64], is_training, False, name="conv_decode3")

    decode_dropout2 = tf.layers.dropout(conv_decode3, rate=(1 - keep_prob), training=is_training, name="decoder_dropout2")
    unpool_2 = unpool_with_argmax(decode_dropout2, ind=pool2_indices, name='unpool_2')
    conv_decode2 = conv_layer_with_bn(initializer, unpool_2, [7, 7, 64, 64], is_training, False, name="conv_decode2")

    decode_dropout1 = tf.layers.dropout(conv_decode2, rate=(1 - keep_prob), training=is_training, name="decoder_dropout1")
    unpool_1 = unpool_with_argmax(decode_dropout1, ind=pool1_indices, name='unpool_1')
    conv_decode1 = conv_layer_with_bn(initializer, unpool_1, [7, 7, 64, 64], is_training, False, name="conv_decode1")

    return conv_classifier(conv_decode1, initializer)


def inference_extended(images, is_training):
    initializer = get_weight_initializer()
    img_d = images.get_shape().as_list()[3]
    conv1_1 = conv_layer_with_bn(initializer, images, [7, 7, img_d, 64], is_training, name="conv1_1")
    conv1_2 = conv_layer_with_bn(initializer, conv1_1, [7, 7, 64, 64], is_training, name="conv1_2")
    pool1, pool1_indices = tf.nn.max_pool_with_argmax(conv1_2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool1')

    conv2_1 = conv_layer_with_bn(initializer, pool1, [7, 7, 64, 64], is_training, name="conv2_1")
    conv2_2 = conv_layer_with_bn(initializer, conv2_1, [7, 7, 64, 64], is_training, name="conv2_2")
    pool2, pool2_indices = tf.nn.max_pool_with_argmax(conv2_2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool2')

    conv3_1 = conv_layer_with_bn(initializer, pool2, [7, 7, 64, 64], is_training, name="conv3_1")
    conv3_2 = conv_layer_with_bn(initializer, conv3_1, [7, 7, 64, 64], is_training, name="conv3_2")
    conv3_3 = conv_layer_with_bn(initializer, conv3_2, [7, 7, 64, 64], is_training, name="conv3_3")
    pool3, pool3_indices = tf.nn.max_pool_with_argmax(conv3_3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool3')

    conv4_1 = conv_layer_with_bn(initializer, pool3, [7, 7, 64, 64], is_training, name="conv4_1")
    conv4_2 = conv_layer_with_bn(initializer, conv4_1, [7, 7, 64, 64], is_training, name="conv4_2")
    conv4_3 = conv_layer_with_bn(initializer, conv4_2, [7, 7, 64, 64], is_training, name="conv4_3")
    pool4, pool4_indices = tf.nn.max_pool_with_argmax(conv4_3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool4')

    conv5_1 = conv_layer_with_bn(initializer, pool4, [7, 7, 64, 64], is_training, name="conv5_1")
    conv5_2 = conv_layer_with_bn(initializer, conv5_1, [7, 7, 64, 64], is_training, name="conv5_2")
    conv5_3 = conv_layer_with_bn(initializer, conv5_2, [7, 7, 64, 64], is_training, name="conv5_3")
    pool5, pool5_indices = tf.nn.max_pool_with_argmax(conv5_3, ksize=[1, 2, 2, 1],
                                                      strides=[1, 2, 2, 1], padding='SAME', name='pool5')
    """ End of encoder """

    """ Start decoder """
    unpool_5 = unpool_with_argmax(pool5, ind=pool5_indices, name="unpool_5")
    conv_decode5_1 = conv_layer_with_bn(initializer, unpool_5, [7, 7, 64, 64], is_training, False, name="conv_decode5_1")
    conv_decode5_2 = conv_layer_with_bn(initializer, conv_decode5_1, [7, 7, 64, 64], is_training, False, name="conv_decode5_2")
    conv_decode5_3 = conv_layer_with_bn(initializer, conv_decode5_2, [7, 7, 64, 64], is_training, False, name="conv_decode5_3")

    unpool_4 = unpool_with_argmax(pool4, ind=pool4_indices, name="unpool_4")
    conv_decode4_1 = conv_layer_with_bn(initializer, unpool_4, [7, 7, 64, 64], is_training, False, name="conv_decode4_1")
    conv_decode4_2 = conv_layer_with_bn(initializer, conv_decode4_1, [7, 7, 64, 64], is_training, False, name="conv_decode4_2")
    conv_decode4_3 = conv_layer_with_bn(initializer, conv_decode4_2, [7, 7, 64, 64], is_training, False, name="conv_decode4_3")

    unpool_3 = unpool_with_argmax(pool3, ind=pool3_indices, name="unpool_3")
    conv_decode3_1 = conv_layer_with_bn(initializer, unpool_3, [7, 7, 64, 64], is_training, False, name="conv_decode3_1")
    conv_decode3_2 = conv_layer_with_bn(initializer, conv_decode3_1, [7, 7, 64, 64], is_training, False, name="conv_decode3_2")
    conv_decode3_3 = conv_layer_with_bn(initializer, conv_decode3_2, [7, 7, 64, 64], is_training, False, name="conv_decode3_3")

    unpool_2 = unpool_with_argmax(pool2, ind=pool2_indices, name="unpool_2")
    conv_decode2_1 = conv_layer_with_bn(initializer, unpool_2, [7, 7, 64, 64], is_training, False, name="conv_decode2_1")
    conv_decode2_2 = conv_layer_with_bn(initializer, conv_decode2_1, [7, 7, 64, 64], is_training, False, name="conv_decode2_2")

    unpool_1 = unpool_with_argmax(pool1, ind=pool1_indices, name="unpool_1")
    conv_decode1_1 = conv_layer_with_bn(initializer, unpool_1, [7, 7, 64, 64], is_training, False, name="conv_decode1_1")
    conv_decode1_2 = conv_layer_with_bn(initializer, conv_decode1_1, [7, 7, 64, 64], is_training, False, name="conv_decode1_2")
    """ End of decoder """

    return conv_classifier(conv_decode1_2, initializer)


def inference_extended_dropout(images, is_training, keep_prob):
    """
      Args:
        images: Images Tensors (placeholder with correct shape, img_h, img_w, img_d)
        is_training: If the model is training or testing
        keep_prob = probability that the layer will be dropped (dropout layer active)
    """

    initializer = get_weight_initializer()
    conv1_1 = conv_layer_with_bn(initializer, images, [7, 7, images.get_shape().as_list()[3], 64], is_training, name="conv1_1")
    conv1_2 = conv_layer_with_bn(initializer, conv1_1, [7, 7, 64, 64], is_training, name="conv1_2")
    pool1, pool1_indices = tf.nn.max_pool_with_argmax(conv1_2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool1')
    dropout1 = tf.layers.dropout(pool1, rate=(1 - keep_prob), training=is_training, name="dropout1")

    conv2_1 = conv_layer_with_bn(initializer, dropout1, [7, 7, 64, 64], is_training, name="conv2_1")
    conv2_2 = conv_layer_with_bn(initializer, conv2_1, [7, 7, 64, 64], is_training, name="conv2_2")
    pool2, pool2_indices = tf.nn.max_pool_with_argmax(conv2_2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool2')
    dropout2 = tf.layers.dropout(pool2, rate=(1 - keep_prob), training=is_training, name="dropout2")

    conv3_1 = conv_layer_with_bn(initializer, dropout2, [7, 7, 64, 64], is_training, name="conv3_1")
    conv3_2 = conv_layer_with_bn(initializer, conv3_1, [7, 7, 64, 64], is_training, name="conv3_2")
    conv3_3 = conv_layer_with_bn(initializer, conv3_2, [7, 7, 64, 64], is_training, name="conv3_3")
    pool3, pool3_indices = tf.nn.max_pool_with_argmax(conv3_3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool3')
    dropout3 = tf.layers.dropout(pool3, rate=(1 - keep_prob), training=is_training, name="dropout3")

    conv4_1 = conv_layer_with_bn(initializer, dropout3, [7, 7, 64, 64], is_training, name="conv4_1")
    conv4_2 = conv_layer_with_bn(initializer, conv4_1, [7, 7, 64, 64], is_training, name="conv4_2")
    conv4_3 = conv_layer_with_bn(initializer, conv4_2, [7, 7, 64, 64], is_training, name="conv4_3")
    pool4, pool4_indices = tf.nn.max_pool_with_argmax(conv4_3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool4')
    dropout4 = tf.layers.dropout(pool4, rate=(1 - keep_prob), training=is_training, name="dropout4")

    conv5_1 = conv_layer_with_bn(initializer, dropout4, [7, 7, 64, 64], is_training, name="conv5_1")
    conv5_2 = conv_layer_with_bn(initializer, conv5_1, [7, 7, 64, 64], is_training, name="conv5_2")
    conv5_3 = conv_layer_with_bn(initializer, conv5_2, [7, 7, 64, 64], is_training, name="conv5_3")
    pool5, pool5_indices = tf.nn.max_pool_with_argmax(conv5_3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME', name='pool5')
    dropout5 = tf.layers.dropout(pool5, rate=(1 - keep_prob), training=is_training, name="dropout5")
    """ End of encoder """

    """ Start decoder """
    unpool_5 = unpool_with_argmax(dropout5, ind=pool5_indices, name='unpool_5')
    conv_decode5_1 = conv_layer_with_bn(initializer, unpool_5, [7, 7, 64, 64], is_training, False, name="conv_decode5_1")
    conv_decode5_2 = conv_layer_with_bn(initializer, conv_decode5_1, [7, 7, 64, 64], is_training, False, name="conv_decode5_2")
    conv_decode5_3 = conv_layer_with_bn(initializer, conv_decode5_2, [7, 7, 64, 64], is_training, False, name="conv_decode5_3")

    dropout4_decode = tf.layers.dropout(conv_decode5_3, rate=(1 - keep_prob), training=is_training, name="dropout4_decode")
    unpool_4 = unpool_with_argmax(dropout4_decode, ind=pool4_indices, name='unpool_4')
    conv_decode4_1 = conv_layer_with_bn(initializer, unpool_4, [7, 7, 64, 64], is_training, False, name="conv_decode4_1")
    conv_decode4_2 = conv_layer_with_bn(initializer, conv_decode4_1, [7, 7, 64, 64], is_training, False, name="conv_decode4_2")
    conv_decode4_3 = conv_layer_with_bn(initializer, conv_decode4_2, [7, 7, 64, 64], is_training, False, name="conv_decode4_3")

    dropout3_decode = tf.layers.dropout(conv_decode4_3, rate=(1 - keep_prob), training=is_training, name="dropout3_decode")
    unpool_3 = unpool_with_argmax(dropout3_decode, ind=pool3_indices, name='unpool_3')
    conv_decode3_1 = conv_layer_with_bn(initializer, unpool_3, [7, 7, 64, 64], is_training, False, name="conv_decode3_1")
    conv_decode3_2 = conv_layer_with_bn(initializer, conv_decode3_1, [7, 7, 64, 64], is_training, False, name="conv_decode3_2")
    conv_decode3_3 = conv_layer_with_bn(initializer, conv_decode3_2, [7, 7, 64, 64], is_training, False, name="conv_decode3_3")

    dropout2_decode = tf.layers.dropout(conv_decode3_3, rate=(1 - keep_prob), training=is_training, name="dropout2_decode")
    unpool_2 = unpool_with_argmax(dropout2_decode, ind=pool2_indices, name='unpool_2')
    conv_decode2_1 = conv_layer_with_bn(initializer, unpool_2, [7, 7, 64, 64], is_training, False, name="conv_decode2_1")
    conv_decode2_2 = conv_layer_with_bn(initializer, conv_decode2_1, [7, 7, 64, 64], is_training, False, name="conv_decode2_2")

    dropout1_decode = tf.layers.dropout(conv_decode2_2, rate=(1 - keep_prob), training=is_training, name="dropout1_deconv")
    unpool_1 = unpool_with_argmax(dropout1_decode, ind=pool1_indices, name='unpool_1')
    conv_decode1_1 = conv_layer_with_bn(initializer, unpool_1, [7, 7, 64, 64], is_training, False, name="conv_decode1_1")
    conv_decode1_2 = conv_layer_with_bn(initializer, conv_decode1_1, [7, 7, 64, 64], is_training, False, name="conv_decode1_2")
    """ End of decoder """

    return conv_classifier(conv_decode1_2, initializer)


def get_weight_initializer():
    if(FLAGS.conv_init == "var_scale"):
        initializer = tf.contrib.layers.variance_scaling_initializer()
    elif(FLAGS.conv_init == "xavier"):
        initializer = tf.contrib.layers.xavier_initializer()
    else:
        raise ValueError("Chosen weight initializer does not exist")
    return initializer
